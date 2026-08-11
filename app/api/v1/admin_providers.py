from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.database import get_db
from app.models.provider import ApiType, ProviderKind
from app.models.user import User
from app.schemas.provider import (
    AggregationMapResponse,
    ConnectivityTestRequest,
    ConnectivityTestResponse,
    ProviderCreate,
    ProviderResponse,
    ProviderToggleResponse,
    ProviderUpdate,
    TypeCatalogResponse,
)
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/admin/providers", tags=["Admin - Providers"])


@router.get("/types", response_model=TypeCatalogResponse)
async def list_type_catalog(_: User = Depends(get_current_admin)) -> TypeCatalogResponse:
    """Catalog of provider kinds (airline/agency/GDS/…) and API types (flight_search/booking/…)."""
    return ProviderService.type_catalog()


@router.get("/aggregation-map", response_model=AggregationMapResponse)
async def aggregation_map(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AggregationMapResponse:
    """
    Shows which providers participate in each aggregate API.

    Example: flight_search → enabled Buddha Air + Yeti + Shree are called by POST /flights/search.
    Use this to know what will be aggregated without guessing.
    """
    return await ProviderService(db).aggregation_map()


@router.get("/adapters", response_model=list[str])
async def list_adapters(_: User = Depends(get_current_admin)) -> list[str]:
    return ProviderService.available_adapters()


@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    enabled_only: bool = Query(default=False),
    api_type: ApiType | None = Query(default=None),
    provider_kind: ProviderKind | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[ProviderResponse]:
    providers = await ProviderService(db).list_providers(
        enabled_only=enabled_only,
        api_type=api_type,
        provider_kind=provider_kind,
    )
    return [ProviderResponse.model_validate(p) for p in providers]


@router.post("", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ProviderResponse:
    provider = await ProviderService(db).create_provider(body)
    return ProviderResponse.model_validate(provider)


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ProviderResponse:
    provider = await ProviderService(db).get_provider(provider_id)
    return ProviderResponse.model_validate(provider)


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: int,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ProviderResponse:
    provider = await ProviderService(db).update_provider(provider_id, body)
    return ProviderResponse.model_validate(provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> None:
    await ProviderService(db).delete_provider(provider_id)


@router.post("/{provider_id}/enable", response_model=ProviderToggleResponse)
async def enable_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ProviderToggleResponse:
    provider = await ProviderService(db).set_enabled(provider_id, True)
    return ProviderToggleResponse(id=provider.id, name=provider.name, enabled=provider.enabled)


@router.post("/{provider_id}/disable", response_model=ProviderToggleResponse)
async def disable_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ProviderToggleResponse:
    provider = await ProviderService(db).set_enabled(provider_id, False)
    return ProviderToggleResponse(id=provider.id, name=provider.name, enabled=provider.enabled)


@router.post("/{provider_id}/test", response_model=ConnectivityTestResponse)
async def test_provider(
    provider_id: int,
    body: ConnectivityTestRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ConnectivityTestResponse:
    sample = body.sample_payload if body else None
    return await ProviderService(db).test_connectivity(provider_id, sample)
