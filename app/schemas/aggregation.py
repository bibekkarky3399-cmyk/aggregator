from typing import Any

from pydantic import BaseModel, Field


class FlightSearchRequest(BaseModel):
    """Unified flight search request accepted by the aggregation API."""

    origin: str = Field(..., min_length=3, max_length=10, description="Origin airport IATA code")
    destination: str = Field(
        ...,
        min_length=3,
        max_length=10,
        description="Destination airport IATA code",
    )
    departure_date: str = Field(..., description="Departure date YYYY-MM-DD")
    return_date: str | None = Field(default=None, description="Return date YYYY-MM-DD")
    adults: int = Field(default=1, ge=1, le=9)
    cabin_class: str = Field(default="economy", description="economy|premium_economy|business|first")
    currency: str = Field(default="NPR", min_length=3, max_length=3)
    providers: list[str] | None = Field(
        default=None,
        description=(
            "Optional provider slugs. When omitted, all enabled providers with "
            "api_type=flight_search are queried (see admin Aggregation Map)."
        ),
    )
    extras: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional fields forwarded through request mapping",
    )


class NormalizedOffer(BaseModel):
    """Common response model for a flight offer from any provider."""

    provider: str
    offer_id: str | None = None
    origin: str | None = None
    destination: str | None = None
    departure_at: str | None = None
    arrival_at: str | None = None
    airline: str | None = None
    flight_number: str | None = None
    cabin_class: str | None = None
    price: float | None = None
    currency: str | None = None
    stops: int | None = None
    duration_minutes: int | None = None
    raw: dict[str, Any] | None = Field(
        default=None,
        description="Provider-specific fields retained for debugging/passthrough",
    )


class ProviderResult(BaseModel):
    provider: str
    success: bool
    latency_ms: float | None = None
    offer_count: int = 0
    error: str | None = None
    offers: list[NormalizedOffer] = Field(default_factory=list)


class AggregateSearchResponse(BaseModel):
    request_id: str
    total_offers: int
    providers_queried: int
    providers_succeeded: int
    providers_failed: int
    results: list[ProviderResult]
    offers: list[NormalizedOffer]


class ProviderOperationResult(BaseModel):
    provider: str
    success: bool
    latency_ms: float | None = None
    error: str | None = None
    data: Any = None


class AggregateOperationRequest(BaseModel):
    """Generic payload for non-search booking operations."""

    providers: list[str] | None = Field(
        default=None,
        description="Optional provider slugs; omit to call all enabled providers for this API type",
    )
    payload: dict[str, Any] = Field(default_factory=dict)


class AggregateOperationResponse(BaseModel):
    request_id: str
    operation: str
    providers_queried: int
    providers_succeeded: int
    providers_failed: int
    results: list[ProviderOperationResult]


class SectorCodesResponse(AggregateOperationResponse):
    pass


class BalanceRequest(BaseModel):
    airline_id: str | None = Field(
        default=None,
        description="Airline code e.g. U4, YT, N9 — omit to query all configured",
    )
    providers: list[str] | None = None


class ReserveRequest(BaseModel):
    flight_id: str = Field(..., description="FlightId / offer_id / Yeti flight_fare_id from availability")
    return_flight_id: str | None = None
    # Yeti B2B (and similar) need sector/date to re-select the fare server-side
    origin: str | None = Field(default=None, description="Origin IATA")
    destination: str | None = None
    departure_date: str | None = Field(default=None, description="YYYY-MM-DD")
    flight_number: str | None = Field(default=None, description="e.g. 673 or YT673")
    fare_code: str | None = Field(default=None, description="e.g. E1")
    adults: int = Field(default=1, ge=1, le=60)
    currency: str = Field(default="NPR")
    group_name: str | None = "AGG"
    contact_name: str | None = None
    contact_email: str | None = None
    contact_mobile: str | None = None
    passengers: list[dict[str, Any]] = Field(default_factory=list)
    providers: list[str] | None = None


class IssueTicketRequest(BaseModel):
    flight_id: str
    return_flight_id: str | None = None
    contact_name: str
    contact_email: str
    contact_mobile: str
    passengers: list[dict[str, Any]] = Field(default_factory=list)
    invoice_party: str | None = None
    pan_no: str | None = None
    providers: list[str] | None = None


class ItineraryRequest(BaseModel):
    pnr: str | None = None
    ticket_no: str | None = None
    airline_id: str | None = None
    providers: list[str] | None = None


class FlightDetailRequest(BaseModel):
    flight_id: str
    providers: list[str] | None = None


class PnrDetailRequest(BaseModel):
    pnr: str
    providers: list[str] | None = None


class SalesReportRequest(BaseModel):
    from_date: str = Field(..., description="YYYY-MM-DD")
    to_date: str = Field(..., description="YYYY-MM-DD")
    providers: list[str] | None = None
