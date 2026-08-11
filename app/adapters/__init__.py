"""Adapter factory — maps adapter_key to concrete adapter classes."""

from __future__ import annotations

from typing import Type

import httpx

from app.adapters.base import ProviderAdapter
from app.adapters.http_adapter import GenericHttpAdapter
from app.models.provider import Provider

_REGISTRY: dict[str, Type[ProviderAdapter]] = {
    "generic": GenericHttpAdapter,
    # Legacy keys — all route to config-driven SOAP/HTTP
    "united_solutions": GenericHttpAdapter,
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
    return adapter_cls(provider, client=client)
