"""Authentication strategies applied by adapters before calling provider APIs."""

from __future__ import annotations

import base64
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.logging import get_logger
from app.models.provider import AuthType

logger = get_logger(__name__)


class AuthStrategy(ABC):
    @abstractmethod
    async def apply(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        auth_config: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> None:
        """Mutate headers/params in place to attach credentials."""


class NoAuthStrategy(AuthStrategy):
    async def apply(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        auth_config: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> None:
        return


class ApiKeyAuthStrategy(AuthStrategy):
    """
    auth_config:
      api_key: "..."
      header_name: "X-API-Key"   (default)
      location: "header" | "query"
      query_param: "api_key"
    """

    async def apply(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        auth_config: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> None:
        api_key = auth_config.get("api_key")
        if not api_key:
            logger.warning("API key auth configured but api_key missing")
            return

        location = (auth_config.get("location") or "header").lower()
        if location == "query":
            params[auth_config.get("query_param") or "api_key"] = api_key
        else:
            header_name = auth_config.get("header_name") or "X-API-Key"
            headers[header_name] = api_key


class BearerAuthStrategy(AuthStrategy):
    """auth_config: { "token": "..." }"""

    async def apply(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        auth_config: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> None:
        token = auth_config.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"


class BasicAuthStrategy(AuthStrategy):
    """auth_config: { "username": "...", "password": "..." }"""

    async def apply(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        auth_config: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> None:
        username = auth_config.get("username", "")
        password = auth_config.get("password", "")
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"


class CustomHeadersAuthStrategy(AuthStrategy):
    """auth_config: { "headers": { "X-Custom": "value" } }"""

    async def apply(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        auth_config: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> None:
        custom = auth_config.get("headers") or {}
        if isinstance(custom, dict):
            headers.update({str(k): str(v) for k, v in custom.items()})


class OAuth2AuthStrategy(AuthStrategy):
    """
    Client-credentials OAuth2 with simple in-memory token cache.

    auth_config:
      token_url: "https://..."
      client_id: "..."
      client_secret: "..."
      scope: "..."
      audience: "..."   (optional)
    """

    _cache: dict[str, tuple[str, float]] = {}

    async def apply(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        auth_config: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> None:
        token_url = auth_config.get("token_url")
        client_id = auth_config.get("client_id")
        client_secret = auth_config.get("client_secret")
        if not token_url or not client_id or not client_secret:
            logger.warning("OAuth2 auth incomplete: need token_url, client_id, client_secret")
            return

        cache_key = f"{token_url}:{client_id}"
        cached = self._cache.get(cache_key)
        now = time.time()
        if cached and cached[1] > now:
            headers["Authorization"] = f"Bearer {cached[0]}"
            return

        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if auth_config.get("scope"):
            data["scope"] = str(auth_config["scope"])
        if auth_config.get("audience"):
            data["audience"] = str(auth_config["audience"])

        response = await client.post(token_url, data=data, timeout=15.0)
        response.raise_for_status()
        payload = response.json()
        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 3600))
        if not access_token:
            raise ValueError("OAuth2 token response missing access_token")

        # Refresh 60s early
        self._cache[cache_key] = (access_token, now + max(expires_in - 60, 30))
        headers["Authorization"] = f"Bearer {access_token}"


def get_auth_strategy(auth_type: AuthType | str) -> AuthStrategy:
    if isinstance(auth_type, str):
        auth_type = AuthType(auth_type)

    strategies: dict[AuthType, AuthStrategy] = {
        AuthType.NONE: NoAuthStrategy(),
        AuthType.API_KEY: ApiKeyAuthStrategy(),
        AuthType.BEARER: BearerAuthStrategy(),
        AuthType.BASIC: BasicAuthStrategy(),
        AuthType.CUSTOM_HEADERS: CustomHeadersAuthStrategy(),
        AuthType.OAUTH2: OAuth2AuthStrategy(),
    }
    return strategies[auth_type]
