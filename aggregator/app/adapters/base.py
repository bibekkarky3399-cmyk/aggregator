"""Provider adapter abstractions (Adapter pattern + SOLID)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models.provider import Provider
from app.schemas.aggregation import NormalizedOffer


@dataclass
class AdapterRequest:
    """Unified inbound request handed to adapters."""

    payload: dict[str, Any]
    operation: str = "search"


@dataclass
class AdapterResponse:
    """Normalized adapter output for a single provider call."""

    success: bool
    offers: list[NormalizedOffer] = field(default_factory=list)
    data: Any = None
    latency_ms: float | None = None
    error: str | None = None
    status_code: int | None = None
    raw: Any = None


class ProviderAdapter(ABC):
    """
    Adapter interface.

    Each provider adapter is responsible for:
    - authentication
    - request transformation
    - calling the provider API
    - response normalization
    """

    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    @abstractmethod
    async def execute(self, request: AdapterRequest) -> AdapterResponse:
        """Execute the primary provider operation and return normalized offers."""

    @abstractmethod
    async def test_connectivity(self, sample_payload: dict[str, Any] | None = None) -> AdapterResponse:
        """Probe provider health / connectivity."""
