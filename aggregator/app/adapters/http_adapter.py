"""Config-driven HTTP adapter — default for all admin-configured providers."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.adapters.auth_strategies import get_auth_strategy
from app.adapters.base import AdapterRequest, AdapterResponse, ProviderAdapter
from app.adapters.mapping import apply_request_mapping, normalize_response
from app.core.logging import get_logger
from app.models.provider import HttpMethod, Provider
from app.schemas.aggregation import NormalizedOffer

logger = get_logger(__name__)


class GenericHttpAdapter(ProviderAdapter):
    """
    Fully configuration-driven adapter.

    New providers can be onboarded via the admin API without writing code,
    as long as request/response mappings and auth config are provided.
    """

    def __init__(self, provider: Provider, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(provider)
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.provider.timeout_seconds),
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_url(self, path: str | None = None) -> str:
        base = self.provider.base_url.rstrip("/") + "/"
        relative = (path or self.provider.endpoint_path or "/").lstrip("/")
        return urljoin(base, relative)

    async def _prepare(
        self,
        payload: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> tuple[dict[str, str], dict[str, Any], dict[str, Any] | None]:
        headers = {"Accept": "application/json", **(self.provider.default_headers or {})}
        query_params: dict[str, Any] = {}
        body = apply_request_mapping(
            payload,
            self.provider.request_mapping or {},
            self.provider.default_params or {},
        )

        auth = get_auth_strategy(self.provider.auth_type)
        await auth.apply(headers, query_params, self.provider.auth_config or {}, client)

        method = self.provider.http_method
        if method == HttpMethod.GET:
            # For GET, mapped body becomes query params
            query_params = {**body, **query_params}
            return headers, query_params, None

        return headers, query_params, body

    async def _send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any],
        json_body: dict[str, Any] | None,
    ) -> httpx.Response:
        client = await self._get_client()
        attempts = max(int(self.provider.max_retries) + 1, 1)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
            reraise=True,
        ):
            with attempt:
                logger.debug(
                    "Calling provider=%s method=%s url=%s attempt=%s",
                    self.provider.slug,
                    method,
                    url,
                    attempt.retry_state.attempt_number,
                )
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params or None,
                    json=json_body,
                    timeout=self.provider.timeout_seconds,
                )
                # Retry transient 5xx
                if response.status_code >= 500:
                    response.raise_for_status()
                return response

        raise RuntimeError("Retry loop exited unexpectedly")

    async def execute(self, request: AdapterRequest) -> AdapterResponse:
        started = time.perf_counter()
        try:
            client = await self._get_client()
            headers, params, body = await self._prepare(request.payload, client)
            url = self._build_url()
            method = self.provider.http_method.value

            response = await self._send(method, url, headers, params, body)
            latency_ms = (time.perf_counter() - started) * 1000

            if response.status_code >= 400:
                return AdapterResponse(
                    success=False,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    error=f"HTTP {response.status_code}: {response.text[:300]}",
                    raw={"status_code": response.status_code, "body": _safe_json(response)},
                )

            raw = _safe_json(response)
            normalized = normalize_response(
                raw,
                self.provider.response_mapping or {},
                self.provider.slug,
            )
            offers = [NormalizedOffer.model_validate(item) for item in normalized]

            return AdapterResponse(
                success=True,
                offers=offers,
                latency_ms=latency_ms,
                status_code=response.status_code,
                raw=raw,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            logger.exception("Provider %s failed: %s", self.provider.slug, exc)
            return AdapterResponse(
                success=False,
                latency_ms=latency_ms,
                error=str(exc),
            )

    async def test_connectivity(self, sample_payload: dict[str, Any] | None = None) -> AdapterResponse:
        started = time.perf_counter()
        try:
            client = await self._get_client()
            path = self.provider.health_check_path
            if path:
                headers = {"Accept": "application/json", **(self.provider.default_headers or {})}
                params: dict[str, Any] = {}
                auth = get_auth_strategy(self.provider.auth_type)
                await auth.apply(headers, params, self.provider.auth_config or {}, client)
                url = self._build_url(path)
                response = await client.get(
                    url,
                    headers=headers,
                    params=params or None,
                    timeout=min(self.provider.timeout_seconds, 15.0),
                )
                latency_ms = (time.perf_counter() - started) * 1000
                ok = response.status_code < 400
                return AdapterResponse(
                    success=ok,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    error=None if ok else f"HTTP {response.status_code}",
                    raw=_safe_json(response),
                )

            # Fall back to a lightweight execute with sample payload
            payload = sample_payload or {
                "origin": "KTM",
                "destination": "PKR",
                "departure_date": "2026-09-15",
                "adults": 1,
                "currency": "NPR",
            }
            return await self.execute(AdapterRequest(payload=payload, operation="connectivity"))
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            return AdapterResponse(success=False, latency_ms=latency_ms, error=str(exc))


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"text": response.text[:1000]}
