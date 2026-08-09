"""Adapter factory — maps adapter_key to concrete adapter classes."""

from __future__ import annotations

from typing import Type

import httpx

from app.adapters.base import ProviderAdapter
from app.adapters.http_adapter import GenericHttpAdapter
from app.adapters.mock_airlines import (
    MockBuddhaAirAdapter,
    MockNepalBookingAdapter,
    MockShreeAirlinesAdapter,
    MockYetiAirlinesAdapter,
)
from app.models.provider import Provider

_REGISTRY: dict[str, Type[ProviderAdapter]] = {
    "generic": GenericHttpAdapter,
    "mock_buddha_air": MockBuddhaAirAdapter,
    "mock_yeti_airlines": MockYetiAirlinesAdapter,
    "mock_shree_airlines": MockShreeAirlinesAdapter,
    "mock_nepal_booking": MockNepalBookingAdapter,
    # Legacy keys kept so older DB rows keep working
    "mock_united_solutions": MockNepalBookingAdapter,
    "mock_skywings": MockBuddhaAirAdapter,
    "mock_aerolink": MockYetiAirlinesAdapter,
}


def register_adapter(key: str, adapter_cls: Type[ProviderAdapter]) -> None:
    """Register a custom adapter class for use via provider.adapter_key."""
    _REGISTRY[key] = adapter_cls


def list_adapter_keys() -> list[str]:
    return sorted(_REGISTRY.keys())


def create_adapter(
    provider: Provider,
    client: httpx.AsyncClient | None = None,
) -> ProviderAdapter:
    key = (provider.adapter_key or "generic").lower()
    adapter_cls = _REGISTRY.get(key, GenericHttpAdapter)
    if adapter_cls is GenericHttpAdapter:
        return GenericHttpAdapter(provider, client=client)
    return adapter_cls(provider)
