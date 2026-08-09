"""Database bootstrap: create tables, seed admin user and demo providers."""

from sqlalchemy import select, text

from app.config import get_settings
from app.core.logging import get_logger
from app.database import AsyncSessionLocal, Base, engine
from app.models.provider import ApiType, AuthType, HttpMethod, Provider, ProviderKind
from app.repositories.user_repository import UserRepository
from app.schemas.provider import ProviderCreate

logger = get_logger(__name__)
settings = get_settings()


DEMO_PROVIDERS = [
    ProviderCreate(
        name="Buddha Air",
        slug="buddha-air",
        description=(
            "Mock Nepal domestic carrier (IATA U4). "
            "Demo search for sectors like KTM–PKR, KTM–BIR, KTM–BWA."
        ),
        enabled=True,
        provider_kind=ProviderKind.AIRLINE,
        api_type=ApiType.FLIGHT_SEARCH,
        base_url="https://mock.buddhaair.local",
        endpoint_path="/v1/domestic/search",
        http_method=HttpMethod.POST,
        auth_type=AuthType.NONE,
        adapter_key="mock_buddha_air",
        default_params={"currency": "NPR", "market": "NP"},
        request_mapping={
            "origin": "origin",
            "destination": "destination",
            "departure_date": "departure_date",
            "adults": "adults",
            "cabin_class": "cabin_class",
            "currency": "currency",
        },
        response_mapping={},
        timeout_seconds=10,
        max_retries=0,
    ),
    ProviderCreate(
        name="Yeti Airlines",
        slug="yeti-airlines",
        description=(
            "Mock Nepal domestic carrier (IATA YT). "
            "Demo search across major domestic cities from Kathmandu."
        ),
        enabled=True,
        provider_kind=ProviderKind.AIRLINE,
        api_type=ApiType.FLIGHT_SEARCH,
        base_url="https://mock.yetiairlines.local",
        endpoint_path="/api/v1/flights/search",
        http_method=HttpMethod.POST,
        auth_type=AuthType.API_KEY,
        auth_config={"api_key": "demo-yeti-key", "header_name": "X-API-Key"},
        adapter_key="mock_yeti_airlines",
        default_params={"currency": "NPR"},
        request_mapping={
            "origin": "from",
            "destination": "to",
            "departure_date": "date",
            "adults": "pax",
        },
        response_mapping={},
        timeout_seconds=10,
        max_retries=0,
    ),
    ProviderCreate(
        name="Shree Airlines",
        slug="shree-airlines",
        description=(
            "Mock Nepal domestic carrier (IATA N9). "
            "Enabled for multi-airline domestic aggregation demos."
        ),
        enabled=True,
        provider_kind=ProviderKind.AIRLINE,
        api_type=ApiType.FLIGHT_SEARCH,
        base_url="https://mock.shreeairlines.local",
        endpoint_path="/domestic/search",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BEARER,
        auth_config={"token": "demo-shree-token"},
        adapter_key="mock_shree_airlines",
        default_params={"currency": "NPR"},
        request_mapping={
            "origin": "departureAirport",
            "destination": "arrivalAirport",
            "departure_date": "flightDate",
            "adults": "adults",
        },
        response_mapping={},
        timeout_seconds=10,
        max_retries=0,
    ),
    # Nepal domestic booking APIs (agency / B2B)
    ProviderCreate(
        name="Nepal · Sector codes",
        slug="nepal-sectors",
        description="Mock Nepal domestic sector list (KTM, PKR, BIR, …).",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.SECTOR_CODES,
        base_url="https://mock.nepalbooking.local",
        endpoint_path="/sectors",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config={"username": "demo", "password": "demo"},
        adapter_key="mock_nepal_booking",
        timeout_seconds=10,
        max_retries=0,
    ),
    ProviderCreate(
        name="Nepal · Agency balance",
        slug="nepal-balance",
        description="Mock agency credit balance per Nepal airline (U4/YT/N9/S1).",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.AGENCY_BALANCE,
        base_url="https://mock.nepalbooking.local",
        endpoint_path="/balance",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config={"username": "demo", "password": "demo"},
        adapter_key="mock_nepal_booking",
        timeout_seconds=10,
        max_retries=0,
    ),
    ProviderCreate(
        name="Nepal · Reservation",
        slug="nepal-reserve",
        description="Mock seat hold — returns PNR + TTL (max ~15 min).",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.FLIGHT_RESERVATION,
        base_url="https://mock.nepalbooking.local",
        endpoint_path="/reserve",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config={"username": "demo", "password": "demo"},
        adapter_key="mock_nepal_booking",
        timeout_seconds=15,
        max_retries=0,
    ),
    ProviderCreate(
        name="Nepal · Issue ticket",
        slug="nepal-ticket",
        description="Mock ticket issue — confirm payment before hold TTL expires.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.ISSUE_TICKET,
        base_url="https://mock.nepalbooking.local",
        endpoint_path="/ticket",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config={"username": "demo", "password": "demo"},
        adapter_key="mock_nepal_booking",
        timeout_seconds=20,
        max_retries=0,
    ),
    ProviderCreate(
        name="Nepal · Get itinerary",
        slug="nepal-itinerary",
        description="Mock PNR / ticket itinerary lookup for Nepal domestic bookings.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.GET_ITINERARY,
        base_url="https://mock.nepalbooking.local",
        endpoint_path="/itinerary",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config={"username": "demo", "password": "demo"},
        adapter_key="mock_nepal_booking",
        timeout_seconds=10,
        max_retries=0,
    ),
    ProviderCreate(
        name="Nepal · Flight detail",
        slug="nepal-flight-detail",
        description="Mock flight detail lookup by FlightId.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.FLIGHT_DETAIL,
        base_url="https://mock.nepalbooking.local",
        endpoint_path="/flight-detail",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config={"username": "demo", "password": "demo"},
        adapter_key="mock_nepal_booking",
        timeout_seconds=10,
        max_retries=0,
    ),
    ProviderCreate(
        name="Nepal · PNR maintenance",
        slug="nepal-pnr",
        description="Mock PNR maintenance link for reschedule or cancel.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.PNR_DETAIL,
        base_url="https://mock.nepalbooking.local",
        endpoint_path="/pnr",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config={"username": "demo", "password": "demo"},
        adapter_key="mock_nepal_booking",
        timeout_seconds=10,
        max_retries=0,
    ),
    ProviderCreate(
        name="Nepal · Sales report",
        slug="nepal-sales",
        description="Mock agency sales report for a date range (NPR).",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.SALES_REPORT,
        base_url="https://mock.nepalbooking.local",
        endpoint_path="/sales-report",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config={"username": "demo", "password": "demo"},
        adapter_key="mock_nepal_booking",
        timeout_seconds=15,
        max_retries=0,
    ),
    ProviderCreate(
        name="Nepal Travel Agency",
        slug="nepal-travel-agency",
        description=(
            "Example Nepal ticket booking agency API for domestic flight search "
            "(disabled template — configure real credentials to use)."
        ),
        enabled=False,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.FLIGHT_SEARCH,
        base_url="https://api.nepal-travel-agency.example",
        endpoint_path="/b2b/domestic/search",
        http_method=HttpMethod.POST,
        auth_type=AuthType.OAUTH2,
        auth_config={
            "token_url": "https://api.nepal-travel-agency.example/oauth/token",
            "client_id": "replace-me",
            "client_secret": "replace-me",
            "scope": "flights.search",
        },
        request_mapping={
            "origin": "originCode",
            "destination": "destinationCode",
            "departure_date": "departDate",
            "adults": "adultCount",
        },
        response_mapping={
            "items": "data.results",
            "offer_id": "offerId",
            "price": "totalAmount",
            "currency": "currency",
            "origin": "origin",
            "destination": "destination",
        },
        adapter_key="generic",
        timeout_seconds=30,
        max_retries=2,
    ),
    ProviderCreate(
        name="Example HTTP Airline",
        slug="example-http",
        description=(
            "Template for a real HTTP airline flight-search API. Disabled by default — "
            "configure base_url, auth, and mappings via admin, then enable."
        ),
        enabled=False,
        provider_kind=ProviderKind.AIRLINE,
        api_type=ApiType.FLIGHT_SEARCH,
        base_url="https://api.example-airline.com",
        endpoint_path="/v1/flights/search",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BEARER,
        auth_config={"token": "replace-me"},
        default_headers={"Content-Type": "application/json", "Accept": "application/json"},
        default_params={},
        request_mapping={
            "origin": "departureAirport",
            "destination": "arrivalAirport",
            "departure_date": "departureDate",
            "return_date": "returnDate",
            "adults": "passengers.adults",
            "cabin_class": "cabin",
            "currency": "currency",
        },
        response_mapping={
            "items": "data.offers",
            "offer_id": "id",
            "origin": "itinerary.origin",
            "destination": "itinerary.destination",
            "departure_at": "itinerary.departureAt",
            "arrival_at": "itinerary.arrivalAt",
            "airline": "validatingCarrier",
            "flight_number": "segments.0.flightNumber",
            "cabin_class": "cabin",
            "price": "price.total",
            "currency": "price.currency",
            "stops": "itinerary.stops",
            "duration_minutes": "itinerary.durationMinutes",
        },
        health_check_path="/health",
        adapter_key="generic",
        timeout_seconds=30,
        max_retries=2,
    ),
    ProviderCreate(
        name="Example ticket agency",
        slug="example-booking",
        description=(
            "Template ticket booking agency endpoint (reserve / issue). "
            "Disabled by default — wire real Nepal agency credentials to use."
        ),
        enabled=False,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.FLIGHT_RESERVATION,
        base_url="https://api.nepal-ticket-agency.example",
        endpoint_path="/v1/reserve",
        http_method=HttpMethod.POST,
        auth_type=AuthType.API_KEY,
        auth_config={"api_key": "replace-me", "header_name": "X-API-Key"},
        request_mapping={
            "flight_id": "flightId",
            "return_flight_id": "returnFlightId",
        },
        response_mapping={
            "items": "data",
            "offer_id": "pnr",
        },
        adapter_key="generic",
        timeout_seconds=45,
        max_retries=1,
    ),
]

# Migrate older demo provider rows to Nepal domestic mocks
_LEGACY_PROVIDER_UPGRADES: dict[str, dict] = {
    "skywings": {
        "name": "Buddha Air",
        "slug": "buddha-air",
        "description": (
            "Mock Nepal domestic carrier (IATA U4). "
            "Demo search for sectors like KTM–PKR, KTM–BIR, KTM–BWA."
        ),
        "base_url": "https://mock.buddhaair.local",
        "endpoint_path": "/v1/domestic/search",
        "adapter_key": "mock_buddha_air",
        "auth_type": AuthType.NONE,
        "auth_config": {},
        "default_params": {"currency": "NPR", "market": "NP"},
        "enabled": True,
        "provider_kind": ProviderKind.AIRLINE,
        "api_type": ApiType.FLIGHT_SEARCH,
    },
    "aerolink": {
        "name": "Yeti Airlines",
        "slug": "yeti-airlines",
        "description": (
            "Mock Nepal domestic carrier (IATA YT). "
            "Demo search across major domestic cities from Kathmandu."
        ),
        "base_url": "https://mock.yetiairlines.local",
        "endpoint_path": "/api/v1/flights/search",
        "adapter_key": "mock_yeti_airlines",
        "auth_type": AuthType.API_KEY,
        "auth_config": {"api_key": "demo-yeti-key", "header_name": "X-API-Key"},
        "default_params": {"currency": "NPR"},
        "enabled": True,
        "provider_kind": ProviderKind.AIRLINE,
        "api_type": ApiType.FLIGHT_SEARCH,
    },
    "travelhub": {
        "name": "Nepal Travel Agency",
        "slug": "nepal-travel-agency",
        "description": (
            "Example Nepal ticket booking agency API for domestic flight search "
            "(disabled template — configure real credentials to use)."
        ),
        "base_url": "https://api.nepal-travel-agency.example",
        "endpoint_path": "/b2b/domestic/search",
        "adapter_key": "generic",
        "enabled": False,
        "provider_kind": ProviderKind.AGENCY,
        "api_type": ApiType.FLIGHT_SEARCH,
    },
    "us-sectors": {
        "name": "Nepal · Sector codes",
        "slug": "nepal-sectors",
        "description": "Mock Nepal domestic sector list (KTM, PKR, BIR, …).",
        "base_url": "https://mock.nepalbooking.local",
        "endpoint_path": "/sectors",
        "adapter_key": "mock_nepal_booking",
        "enabled": True,
        "provider_kind": ProviderKind.AGENCY,
        "api_type": ApiType.SECTOR_CODES,
    },
    "us-balance": {
        "name": "Nepal · Agency balance",
        "slug": "nepal-balance",
        "description": "Mock agency credit balance per Nepal airline (U4/YT/N9/S1).",
        "base_url": "https://mock.nepalbooking.local",
        "endpoint_path": "/balance",
        "adapter_key": "mock_nepal_booking",
        "enabled": True,
        "provider_kind": ProviderKind.AGENCY,
        "api_type": ApiType.AGENCY_BALANCE,
    },
    "us-reserve": {
        "name": "Nepal · Reservation",
        "slug": "nepal-reserve",
        "description": "Mock seat hold — returns PNR + TTL (max ~15 min).",
        "base_url": "https://mock.nepalbooking.local",
        "endpoint_path": "/reserve",
        "adapter_key": "mock_nepal_booking",
        "enabled": True,
        "provider_kind": ProviderKind.AGENCY,
        "api_type": ApiType.FLIGHT_RESERVATION,
    },
    "us-ticket": {
        "name": "Nepal · Issue ticket",
        "slug": "nepal-ticket",
        "description": "Mock ticket issue — confirm payment before hold TTL expires.",
        "base_url": "https://mock.nepalbooking.local",
        "endpoint_path": "/ticket",
        "adapter_key": "mock_nepal_booking",
        "enabled": True,
        "provider_kind": ProviderKind.AGENCY,
        "api_type": ApiType.ISSUE_TICKET,
    },
    "us-itinerary": {
        "name": "Nepal · Get itinerary",
        "slug": "nepal-itinerary",
        "description": "Mock PNR / ticket itinerary lookup for Nepal domestic bookings.",
        "base_url": "https://mock.nepalbooking.local",
        "endpoint_path": "/itinerary",
        "adapter_key": "mock_nepal_booking",
        "enabled": True,
        "provider_kind": ProviderKind.AGENCY,
        "api_type": ApiType.GET_ITINERARY,
    },
    "us-flight-detail": {
        "name": "Nepal · Flight detail",
        "slug": "nepal-flight-detail",
        "description": "Mock flight detail lookup by FlightId.",
        "base_url": "https://mock.nepalbooking.local",
        "endpoint_path": "/flight-detail",
        "adapter_key": "mock_nepal_booking",
        "enabled": True,
        "provider_kind": ProviderKind.AGENCY,
        "api_type": ApiType.FLIGHT_DETAIL,
    },
    "us-pnr": {
        "name": "Nepal · PNR maintenance",
        "slug": "nepal-pnr",
        "description": "Mock PNR maintenance link for reschedule or cancel.",
        "base_url": "https://mock.nepalbooking.local",
        "endpoint_path": "/pnr",
        "adapter_key": "mock_nepal_booking",
        "enabled": True,
        "provider_kind": ProviderKind.AGENCY,
        "api_type": ApiType.PNR_DETAIL,
    },
    "us-sales": {
        "name": "Nepal · Sales report",
        "slug": "nepal-sales",
        "description": "Mock agency sales report for a date range (NPR).",
        "base_url": "https://mock.nepalbooking.local",
        "endpoint_path": "/sales-report",
        "adapter_key": "mock_nepal_booking",
        "enabled": True,
        "provider_kind": ProviderKind.AGENCY,
        "api_type": ApiType.SALES_REPORT,
    },
}


async def _ensure_sqlite_columns(connection) -> None:
    """Add new classification columns to existing SQLite DBs without wiping data."""
    if not str(engine.url).startswith("sqlite"):
        return

    result = await connection.execute(text("PRAGMA table_info(providers)"))
    rows = result.fetchall()
    if not rows:
        return

    existing = {row[1] for row in rows}
    alterations = []
    if "provider_kind" not in existing:
        alterations.append(
            "ALTER TABLE providers ADD COLUMN provider_kind VARCHAR(32) "
            "DEFAULT 'airline' NOT NULL"
        )
    if "api_type" not in existing:
        alterations.append(
            "ALTER TABLE providers ADD COLUMN api_type VARCHAR(32) "
            "DEFAULT 'flight_search' NOT NULL"
        )
    for stmt in alterations:
        await connection.execute(text(stmt))
        logger.info("Applied schema patch: %s", stmt)


async def _normalize_provider_classifications(connection) -> None:
    """Map removed kinds/types onto airline / agency ticket-booking only."""
    await connection.execute(
        text(
            "UPDATE providers SET provider_kind = 'agency' "
            "WHERE provider_kind IN ('gds', 'consolidator', 'ota', 'other')"
        )
    )
    await connection.execute(
        text(
            "UPDATE providers SET api_type = 'flight_reservation' "
            "WHERE api_type IN ('flight_booking', 'flight_cancel')"
        )
    )
    await connection.execute(
        text(
            "UPDATE providers SET api_type = 'flight_search' "
            "WHERE api_type IN ("
            "'hotel_search', 'hotel_booking', 'car_rental', "
            "'ancillary', 'other', 'flight_status'"
            ")"
        )
    )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_sqlite_columns(conn)
        await _normalize_provider_classifications(conn)
    logger.info("Database tables ensured")

    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        if await repo.count() == 0:
            await repo.create_admin(
                username=settings.admin_username,
                email=settings.admin_email,
                password=settings.admin_password,
            )
            logger.info("Bootstrap admin user created: %s", settings.admin_username)

        result = await session.execute(select(Provider))
        existing = list(result.scalars().all())
        if not existing:
            for demo in DEMO_PROVIDERS:
                session.add(Provider(**demo.model_dump()))
            logger.info("Seeded %s demo providers", len(DEMO_PROVIDERS))
        else:
            slugs = {p.slug for p in existing}
            for provider in existing:
                upgrade = _LEGACY_PROVIDER_UPGRADES.get(provider.slug)
                if upgrade:
                    # Avoid slug collisions if Nepal providers already exist
                    target_slug = upgrade["slug"]
                    if target_slug in slugs and target_slug != provider.slug:
                        provider.enabled = False
                        logger.info(
                            "Legacy provider %s left disabled; %s already exists",
                            provider.slug,
                            target_slug,
                        )
                    else:
                        for key, value in upgrade.items():
                            setattr(provider, key, value)
                        logger.info("Upgraded legacy provider to %s", target_slug)
                elif provider.slug == "example-http":
                    provider.provider_kind = ProviderKind.AIRLINE
                    provider.api_type = ApiType.FLIGHT_SEARCH
                elif provider.slug == "example-booking":
                    provider.name = "Example ticket agency"
                    provider.provider_kind = ProviderKind.AGENCY
                    provider.api_type = ApiType.FLIGHT_RESERVATION
                    provider.base_url = "https://api.nepal-ticket-agency.example"
                    provider.endpoint_path = "/v1/reserve"
                    provider.description = (
                        "Template ticket booking agency endpoint (reserve / issue). "
                        "Disabled by default — wire real Nepal agency credentials to use."
                    )

            # Refresh slug set after upgrades
            await session.flush()
            result = await session.execute(select(Provider))
            existing = list(result.scalars().all())
            slugs = {p.slug for p in existing}
            for demo in DEMO_PROVIDERS:
                if demo.slug not in slugs:
                    session.add(Provider(**demo.model_dump()))
                    logger.info("Seeded additional provider: %s", demo.slug)

        await session.commit()
