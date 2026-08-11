from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import create_adapter, list_adapter_keys
from app.models.provider import API_TYPE_CATALOG, ApiType, Provider, ProviderKind
from app.repositories.provider_repository import ProviderRepository
from app.schemas.provider import (
    AggregationMapEntry,
    AggregationMapResponse,
    AggregationParticipant,
    ConnectivityTestResponse,
    ProviderCreate,
    ProviderUpdate,
    TypeCatalogResponse,
    build_type_catalog,
)
from app.services.aggregation import AggregationService


class ProviderService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = ProviderRepository(db)

    async def list_providers(
        self,
        *,
        enabled_only: bool = False,
        api_type: ApiType | None = None,
        provider_kind: ProviderKind | None = None,
    ) -> list[Provider]:
        return await self.repo.list_all(
            enabled_only=enabled_only,
            api_type=api_type,
            provider_kind=provider_kind,
        )

    async def get_provider(self, provider_id: int) -> Provider:
        provider = await self.repo.get_by_id(provider_id)
        if not provider:
            from app.core.exceptions import NotFoundError

            raise NotFoundError(f"Provider {provider_id} not found")
        return provider

    async def create_provider(self, data: ProviderCreate) -> Provider:
        return await self.repo.create(data)

    async def update_provider(self, provider_id: int, data: ProviderUpdate) -> Provider:
        return await self.repo.update(provider_id, data)

    async def delete_provider(self, provider_id: int) -> None:
        await self.repo.delete(provider_id)

    async def set_enabled(self, provider_id: int, enabled: bool) -> Provider:
        return await self.repo.set_enabled(provider_id, enabled)

    async def resolve_for_aggregation(
        self,
        *,
        api_type: ApiType,
        slugs: list[str] | None = None,
    ) -> list[Provider]:
        """Resolve enabled providers that participate in a given aggregate operation."""
        if slugs:
            return await self.repo.get_by_slugs(slugs, enabled_only=True, api_type=api_type)
        return await self.repo.list_all(enabled_only=True, api_type=api_type)

    async def aggregation_map(self) -> AggregationMapResponse:
        """Admin view: which providers are wired to each API type / aggregate route."""
        all_providers = await self.repo.list_all(enabled_only=False)
        by_type: dict[ApiType, list[Provider]] = {api: [] for api in ApiType}
        for provider in all_providers:
            by_type.setdefault(provider.api_type, []).append(provider)

        entries: list[AggregationMapEntry] = []
        for api_type, meta in API_TYPE_CATALOG.items():
            providers = by_type.get(api_type, [])
            enabled = [p for p in providers if p.enabled]
            entries.append(
                AggregationMapEntry(
                    api_type=api_type,
                    label=meta["label"],
                    description=meta["description"],
                    aggregate_endpoint=meta.get("aggregate_endpoint"),
                    group=meta.get("group"),
                    enabled_count=len(enabled),
                    total_count=len(providers),
                    providers=[
                        AggregationParticipant(
                            id=p.id,
                            name=p.name,
                            slug=p.slug,
                            provider_kind=p.provider_kind,
                            enabled=p.enabled,
                            adapter_key=p.adapter_key,
                        )
                        for p in providers
                    ],
                )
            )
        return AggregationMapResponse(entries=entries)

    async def test_connectivity(
        self,
        provider_id: int,
        sample_payload: dict[str, Any] | None = None,
    ) -> ConnectivityTestResponse:
        provider = await self.get_provider(provider_id)
        adapter = create_adapter(provider)
        try:
            result = await adapter.test_connectivity(sample_payload)
            preview = None
            if result.raw is not None:
                preview = result.raw if not isinstance(result.raw, (dict, list)) else result.raw
                if isinstance(preview, (dict, list)):
                    preview_str = str(preview)
                    if len(preview_str) > 2000:
                        preview = {"truncated": preview_str[:2000]}

            message = "Connectivity OK" if result.success else (result.error or "Connectivity failed")
            if result.success and isinstance(result.raw, dict) and result.raw.get("note"):
                message = str(result.raw["note"])

            return ConnectivityTestResponse(
                success=result.success,
                provider_id=provider.id,
                provider_name=provider.name,
                status_code=result.status_code,
                latency_ms=result.latency_ms,
                message=message,
                sample_normalized=(
                    result.offers[0].model_dump() if result.offers else None
                ),
                raw_preview=preview,
            )
        finally:
            close = getattr(adapter, "aclose", None)
            if callable(close):
                await close()

    @staticmethod
    def available_adapters() -> list[str]:
        return list_adapter_keys()

    @staticmethod
    def type_catalog() -> TypeCatalogResponse:
        return build_type_catalog()

    async def build_aggregation_service(
        self,
        *,
        api_type: ApiType,
        slugs: list[str] | None = None,
    ) -> AggregationService:
        providers = await self.resolve_for_aggregation(api_type=api_type, slugs=slugs)
        return AggregationService(providers)
