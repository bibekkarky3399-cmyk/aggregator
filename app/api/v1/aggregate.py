from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_api_access
from app.database import get_db
from app.models.provider import ApiType
from app.schemas.aggregation import AggregateSearchResponse, FlightSearchRequest
from app.services.api_key_service import ApiPrincipal
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/flights", tags=["Aggregation"])


@router.post("/search", response_model=AggregateSearchResponse)
async def search_flights(
    body: FlightSearchRequest,
    db: AsyncSession = Depends(get_db),
    _: ApiPrincipal = Depends(require_api_access(ApiType.FLIGHT_SEARCH)),
) -> AggregateSearchResponse:
    """
    Aggregate live flight offers from enabled providers with api_type=flight_search.

    Optionally narrow further with `providers` (slugs). Provider failures are isolated.
    Results are not persisted. Requires API key (or admin JWT when bypass is enabled).
    """
    service = await ProviderService(db).build_aggregation_service(
        api_type=ApiType.FLIGHT_SEARCH,
        slugs=body.providers,
    )
    return await service.search(body)
