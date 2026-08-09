import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthType(str, enum.Enum):
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    OAUTH2 = "oauth2"
    BASIC = "basic"
    CUSTOM_HEADERS = "custom_headers"


class HttpMethod(str, enum.Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ProviderKind(str, enum.Enum):
    """Who the provider is — airlines or ticket booking agencies only."""

    AIRLINE = "airline"  # Direct carrier API (Buddha Air, Yeti, Shree, …)
    AGENCY = "agency"  # Ticket booking / B2B agency API


class ApiType(str, enum.Enum):
    """Nepal domestic airline & agency ticket-booking operations."""

    SECTOR_CODES = "sector_codes"
    AGENCY_BALANCE = "agency_balance"
    FLIGHT_SEARCH = "flight_search"
    FLIGHT_RESERVATION = "flight_reservation"
    ISSUE_TICKET = "issue_ticket"
    GET_ITINERARY = "get_itinerary"
    FLIGHT_DETAIL = "flight_detail"
    PNR_DETAIL = "pnr_detail"
    SALES_REPORT = "sales_report"


# Human-readable catalog used by admin APIs / UI
API_TYPE_CATALOG: dict[ApiType, dict[str, str]] = {
    ApiType.SECTOR_CODES: {
        "label": "Sector codes",
        "description": "List Nepal domestic sector codes and airport names.",
        "aggregate_endpoint": "GET /api/v1/booking/sectors",
        "group": "reference",
    },
    ApiType.AGENCY_BALANCE: {
        "label": "Agency balance",
        "description": "Check agency credit balance per Nepal airline.",
        "aggregate_endpoint": "POST /api/v1/booking/balance",
        "group": "agency",
    },
    ApiType.FLIGHT_SEARCH: {
        "label": "Flight availability",
        "description": "Search available Nepal domestic flights for a sector/date.",
        "aggregate_endpoint": "POST /api/v1/flights/search",
        "group": "booking",
    },
    ApiType.FLIGHT_RESERVATION: {
        "label": "Reservation (hold)",
        "description": "Hold seats on a selected flight; returns PNR + TTL.",
        "aggregate_endpoint": "POST /api/v1/booking/reserve",
        "group": "booking",
    },
    ApiType.ISSUE_TICKET: {
        "label": "Issue ticket",
        "description": "Confirm payment and issue tickets before hold TTL expires.",
        "aggregate_endpoint": "POST /api/v1/booking/ticket",
        "group": "booking",
    },
    ApiType.GET_ITINERARY: {
        "label": "Get itinerary",
        "description": "Fetch PNR / ticket itinerary details.",
        "aggregate_endpoint": "POST /api/v1/booking/itinerary",
        "group": "post_sale",
    },
    ApiType.FLIGHT_DETAIL: {
        "label": "Flight detail",
        "description": "Lookup details for a Nepal domestic FlightId.",
        "aggregate_endpoint": "POST /api/v1/booking/flight-detail",
        "group": "reference",
    },
    ApiType.PNR_DETAIL: {
        "label": "PNR maintenance",
        "description": "PNR maintenance link / detail for reschedule or cancel.",
        "aggregate_endpoint": "POST /api/v1/booking/pnr",
        "group": "post_sale",
    },
    ApiType.SALES_REPORT: {
        "label": "Sales report",
        "description": "Agency sales report for a date range (NPR).",
        "aggregate_endpoint": "POST /api/v1/booking/sales-report",
        "group": "agency",
    },
}

PROVIDER_KIND_CATALOG: dict[ProviderKind, dict[str, str]] = {
    ProviderKind.AIRLINE: {
        "label": "Airline",
        "description": "Direct Nepal airline / carrier API",
    },
    ProviderKind.AGENCY: {
        "label": "Ticket booking agency",
        "description": "B2B ticket booking / agency API (availability through ticketing)",
    },
}


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Classification: who + what API operation
    provider_kind: Mapped[ProviderKind] = mapped_column(
        Enum(ProviderKind, values_callable=lambda obj: [e.value for e in obj]),
        default=ProviderKind.AIRLINE,
        nullable=False,
        index=True,
    )
    api_type: Mapped[ApiType] = mapped_column(
        Enum(ApiType, values_callable=lambda obj: [e.value for e in obj]),
        default=ApiType.FLIGHT_SEARCH,
        nullable=False,
        index=True,
    )

    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Relative path for the primary operation, e.g. "/v1/flights/search"
    endpoint_path: Mapped[str] = mapped_column(String(500), nullable=False, default="/")
    http_method: Mapped[HttpMethod] = mapped_column(
        Enum(HttpMethod, values_callable=lambda obj: [e.value for e in obj]),
        default=HttpMethod.POST,
        nullable=False,
    )

    auth_type: Mapped[AuthType] = mapped_column(
        Enum(AuthType, values_callable=lambda obj: [e.value for e in obj]),
        default=AuthType.NONE,
        nullable=False,
    )
    # Flexible auth config: api_key, header_name, token_url, client_id, username, etc.
    auth_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Static headers merged into every request
    default_headers: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Default query/body params merged into every request
    default_params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Maps unified request fields -> provider request fields
    # Example: {"origin": "from", "destination": "to", "departure_date": "date"}
    request_mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Maps provider response paths -> unified response fields
    # Example: {"items": "data.flights", "item_id": "id", "price": "fare.total"}
    response_mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Optional health-check endpoint (relative to base_url)
    health_check_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timeout_seconds: Mapped[float] = mapped_column(default=30.0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    # Adapter class key; "generic" uses config-driven HTTP adapter
    adapter_key: Mapped[str] = mapped_column(String(100), default="generic", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
