"""Concurrent aggregation of enabled provider adapters."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx

from app.adapters import create_adapter
from app.adapters.base import AdapterRequest, AdapterResponse
from app.adapters.http_adapter import GenericHttpAdapter
from app.config import get_settings
from app.core.logging import get_logger
from app.models.provider import Provider
from app.schemas.aggregation import (
    AggregateOperationResponse,
    AggregateSearchResponse,
    FlightSearchRequest,
    NormalizedOffer,
    ProviderOperationResult,
    ProviderResult,
)
from app.services.metrics import metrics_store

logger = get_logger(__name__)
settings = get_settings()


class AggregationService:
    """
    Calls enabled providers concurrently, isolates failures,
    and returns a single unified response. Does not persist results.
    """

    def __init__(self, providers: list[Provider]) -> None:
        self.providers = providers

    async def search(self, request: FlightSearchRequest) -> AggregateSearchResponse:
        request_id = str(uuid.uuid4())
        payload = request.model_dump()

        if not self.providers:
            return AggregateSearchResponse(
                request_id=request_id,
                total_offers=0,
                providers_queried=0,
                providers_succeeded=0,
                providers_failed=0,
                results=[],
                offers=[],
            )

        async with httpx.AsyncClient() as client:
            tasks = [
                self._call_provider(provider, payload, client, operation="flight_search")
                for provider in self.providers
            ]
            try:
                outcomes = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=settings.aggregation_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.error("Aggregation timed out after %ss", settings.aggregation_timeout_seconds)
                outcomes = [
                    ProviderResult(
                        provider=p.slug,
                        success=False,
                        error="Aggregation timeout",
                    )
                    for p in self.providers
                ]

        results: list[ProviderResult] = []
        all_offers: list[NormalizedOffer] = []

        for provider, outcome in zip(self.providers, outcomes):
            if isinstance(outcome, ProviderResult):
                results.append(outcome)
                all_offers.extend(outcome.offers)
            elif isinstance(outcome, Exception):
                logger.exception("Unhandled provider error for %s", provider.slug)
                results.append(
                    ProviderResult(
                        provider=provider.slug,
                        success=False,
                        error=str(outcome),
                    )
                )
            else:
                results.append(
                    ProviderResult(
                        provider=provider.slug,
                        success=False,
                        error="Unexpected aggregation outcome",
                    )
                )

        # Sort offers by price when available
        all_offers.sort(key=lambda o: (o.price is None, o.price or 0.0))

        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded

        metrics_store.record_aggregation(
            providers_queried=len(results),
            providers_succeeded=succeeded,
            providers_failed=failed,
            total_offers=len(all_offers),
            results=[r.model_dump() for r in results],
        )

        return AggregateSearchResponse(
            request_id=request_id,
            total_offers=len(all_offers),
            providers_queried=len(results),
            providers_succeeded=succeeded,
            providers_failed=failed,
            results=results,
            offers=all_offers,
        )

    async def execute(
        self,
        *,
        operation: str,
        payload: dict[str, Any],
    ) -> AggregateOperationResponse:
        """Run a non-search booking operation across enabled providers."""
        request_id = str(uuid.uuid4())
        if not self.providers:
            return AggregateOperationResponse(
                request_id=request_id,
                operation=operation,
                providers_queried=0,
                providers_succeeded=0,
                providers_failed=0,
                results=[],
            )

        async with httpx.AsyncClient() as client:
            tasks = [
                self._call_operation(provider, payload, client, operation)
                for provider in self.providers
            ]
            try:
                outcomes = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=settings.aggregation_timeout_seconds,
                )
            except asyncio.TimeoutError:
                outcomes = [
                    ProviderOperationResult(
                        provider=p.slug,
                        success=False,
                        error="Aggregation timeout",
                    )
                    for p in self.providers
                ]

        results: list[ProviderOperationResult] = []
        for provider, outcome in zip(self.providers, outcomes):
            if isinstance(outcome, ProviderOperationResult):
                results.append(outcome)
            elif isinstance(outcome, Exception):
                results.append(
                    ProviderOperationResult(
                        provider=provider.slug,
                        success=False,
                        error=str(outcome),
                    )
                )
            else:
                results.append(
                    ProviderOperationResult(
                        provider=provider.slug,
                        success=False,
                        error="Unexpected aggregation outcome",
                    )
                )

        succeeded = sum(1 for r in results if r.success)
        metrics_store.record_aggregation(
            providers_queried=len(results),
            providers_succeeded=succeeded,
            providers_failed=len(results) - succeeded,
            total_offers=0,
            results=[
                {
                    "provider": r.provider,
                    "success": r.success,
                    "latency_ms": r.latency_ms,
                    "offer_count": 0,
                }
                for r in results
            ],
        )
        return AggregateOperationResponse(
            request_id=request_id,
            operation=operation,
            providers_queried=len(results),
            providers_succeeded=succeeded,
            providers_failed=len(results) - succeeded,
            results=results,
        )

    async def _call_provider(
        self,
        provider: Provider,
        payload: dict[str, Any],
        client: httpx.AsyncClient,
        operation: str = "flight_search",
    ) -> ProviderResult:
        adapter = create_adapter(provider, client=client)
        try:
            response: AdapterResponse = await adapter.execute(
                AdapterRequest(payload=payload, operation=operation)
            )
            return ProviderResult(
                provider=provider.slug,
                success=response.success,
                latency_ms=response.latency_ms,
                offer_count=len(response.offers),
                error=response.error,
                offers=response.offers if response.success else [],
            )
        finally:
            if isinstance(adapter, GenericHttpAdapter) and adapter._owns_client:
                await adapter.aclose()

    async def _call_operation(
        self,
        provider: Provider,
        payload: dict[str, Any],
        client: httpx.AsyncClient,
        operation: str,
    ) -> ProviderOperationResult:
        adapter = create_adapter(provider, client=client)
        try:
            response: AdapterResponse = await adapter.execute(
                AdapterRequest(payload=payload, operation=operation)
            )
            return ProviderOperationResult(
                provider=provider.slug,
                success=response.success,
                latency_ms=response.latency_ms,
                error=response.error,
                data=response.data if response.success else None,
            )
        finally:
            if isinstance(adapter, GenericHttpAdapter) and adapter._owns_client:
                await adapter.aclose()
