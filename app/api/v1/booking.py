"""Nepal domestic booking API aggregation routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.provider import ApiType
from app.schemas.aggregation import (
    AggregateOperationResponse,
    BalanceRequest,
    FlightDetailRequest,
    IssueTicketRequest,
    ItineraryRequest,
    PnrDetailRequest,
    ReserveRequest,
    SalesReportRequest,
)
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/booking", tags=["Nepal Booking"])


async def _run(
    db: AsyncSession,
    *,
    api_type: ApiType,
    operation: str,
    payload: dict,
    slugs: list[str] | None,
) -> AggregateOperationResponse:
    service = await ProviderService(db).build_aggregation_service(
        api_type=api_type,
        slugs=slugs,
    )
    return await service.execute(operation=operation, payload=payload)


@router.get("/sectors", response_model=AggregateOperationResponse)
async def sector_codes(db: AsyncSession = Depends(get_db)) -> AggregateOperationResponse:
    """Aggregate Nepal domestic airport/sector lists from enabled providers."""
    return await _run(
        db,
        api_type=ApiType.SECTOR_CODES,
        operation="sector_codes",
        payload={},
        slugs=None,
    )


@router.post("/balance", response_model=AggregateOperationResponse)
async def check_balance(
    body: BalanceRequest,
    db: AsyncSession = Depends(get_db),
) -> AggregateOperationResponse:
    """Aggregate agency credit balances for Nepal airlines."""
    return await _run(
        db,
        api_type=ApiType.AGENCY_BALANCE,
        operation="agency_balance",
        payload={"airline_id": body.airline_id},
        slugs=body.providers,
    )


@router.post("/reserve", response_model=AggregateOperationResponse)
async def reserve(
    body: ReserveRequest,
    db: AsyncSession = Depends(get_db),
) -> AggregateOperationResponse:
    """Hold seats; returns PNR + TTL (not persisted)."""
    return await _run(
        db,
        api_type=ApiType.FLIGHT_RESERVATION,
        operation="flight_reservation",
        payload={
            "flight_id": body.flight_id,
            "return_flight_id": body.return_flight_id,
            "origin": body.origin,
            "destination": body.destination,
            "departure_date": body.departure_date,
            "flight_number": body.flight_number,
            "fare_code": body.fare_code,
            "adults": body.adults,
            "currency": body.currency,
            "group_name": body.group_name,
            "contact_name": body.contact_name,
            "contact_email": body.contact_email,
            "contact_mobile": body.contact_mobile,
            "passengers": body.passengers,
        },
        slugs=body.providers,
    )


@router.post("/ticket", response_model=AggregateOperationResponse)
async def issue_ticket(
    body: IssueTicketRequest,
    db: AsyncSession = Depends(get_db),
) -> AggregateOperationResponse:
    """Confirm payment and issue tickets before hold TTL expires."""
    return await _run(
        db,
        api_type=ApiType.ISSUE_TICKET,
        operation="issue_ticket",
        payload=body.model_dump(exclude={"providers"}),
        slugs=body.providers,
    )


@router.post("/itinerary", response_model=AggregateOperationResponse)
async def get_itinerary(
    body: ItineraryRequest,
    db: AsyncSession = Depends(get_db),
) -> AggregateOperationResponse:
    """Fetch PNR / ticket itinerary details."""
    return await _run(
        db,
        api_type=ApiType.GET_ITINERARY,
        operation="get_itinerary",
        payload=body.model_dump(exclude={"providers"}),
        slugs=body.providers,
    )


@router.post("/flight-detail", response_model=AggregateOperationResponse)
async def flight_detail(
    body: FlightDetailRequest,
    db: AsyncSession = Depends(get_db),
) -> AggregateOperationResponse:
    """Lookup Nepal domestic flight details by FlightId."""
    return await _run(
        db,
        api_type=ApiType.FLIGHT_DETAIL,
        operation="flight_detail",
        payload={"flight_id": body.flight_id},
        slugs=body.providers,
    )


@router.post("/pnr", response_model=AggregateOperationResponse)
async def pnr_detail(
    body: PnrDetailRequest,
    db: AsyncSession = Depends(get_db),
) -> AggregateOperationResponse:
    """PNR maintenance URL / detail for reschedule or cancel."""
    return await _run(
        db,
        api_type=ApiType.PNR_DETAIL,
        operation="pnr_detail",
        payload={"pnr": body.pnr},
        slugs=body.providers,
    )


@router.post("/sales-report", response_model=AggregateOperationResponse)
async def sales_report(
    body: SalesReportRequest,
    db: AsyncSession = Depends(get_db),
) -> AggregateOperationResponse:
    """Aggregate agency sales report for a date range."""
    return await _run(
        db,
        api_type=ApiType.SALES_REPORT,
        operation="sales_report",
        payload={"from_date": body.from_date, "to_date": body.to_date},
        slugs=body.providers,
    )
