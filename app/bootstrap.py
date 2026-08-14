"""Database bootstrap: create tables, seed admin, United Solutions providers only."""

from sqlalchemy import select, text

from app.config import get_settings
from app.core.logging import get_logger
from app.database import AsyncSessionLocal, Base, engine
from app.models import api_client as _api_client_models  # noqa: F401 — register tables
from app.models.provider import ApiType, AuthType, HttpMethod, Provider, ProviderKind
from app.models.user import User  # noqa: F401
from app.repositories.api_client_repository import AuthSettingsRepository
from app.repositories.user_repository import UserRepository
from app.schemas.provider import ProviderCreate

logger = get_logger(__name__)
settings = get_settings()

US_SOAP_NS = "http://booking.us.org/"
US_ENDPOINT_DEFAULT = "http://dev.usbooking.org/us/UnitedSolutions"


def _us_auth(soap: dict) -> dict:
    """Credentials + SOAP operation template for a United Solutions provider row."""
    return {
        "user_id": "TSTAPI",
        "password": "PASSWORD",
        "agency_id": "PLZ178",
        "client_ip": "TSTAPI",
        "endpoint": US_ENDPOINT_DEFAULT,
        "soap": {"namespace": US_SOAP_NS, **soap},
    }


# Only United Solutions — config-driven SOAP via generic adapter.
DEMO_PROVIDERS = [
    ProviderCreate(
        name="United Solutions · Sector codes",
        slug="us-sectors",
        description="SOAP SectorCode. Credentials via Admin or US_* env.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.SECTOR_CODES,
        base_url=US_ENDPOINT_DEFAULT,
        endpoint_path="",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config=_us_auth(
            {
                "operation": "SectorCode",
                "response_mode": "data",
                "items_tag": "Sector",
                "fields": {"strUserId": "$auth.user_id"},
            }
        ),
        adapter_key="generic",
        timeout_seconds=90,
        max_retries=0,
    ),
    ProviderCreate(
        name="United Solutions · Availability",
        slug="us-search",
        description="SOAP FlightAvailability. offer_id = FlightId GUID.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.FLIGHT_SEARCH,
        base_url=US_ENDPOINT_DEFAULT,
        endpoint_path="",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config=_us_auth(
            {
                "operation": "FlightAvailability",
                "response_mode": "offers",
                "items_tag": "Availability",
                "wrap_tags": ["Outbound", "Inbound"],
                "fields": {
                    "strUserId": "$auth.user_id",
                    "strPassword": "$auth.password",
                    "strAgencyId": "$auth.agency_id",
                    "strSectorFrom": "$payload.origin|upper",
                    "strSectorTo": "$payload.destination|upper",
                    "strFlightDate": "$payload.departure_date|api_date",
                    "strReturnDate": "$payload.return_date|api_date|optional",
                    "strTripType": "O",
                    "strNationality": "NP",
                    "intAdult": "$payload.adults|str",
                    "intChild": "0",
                    "strClientIP": "$auth.client_ip",
                },
                "item_map": {
                    "offer_id": "FlightId",
                    "origin": "Departure",
                    "destination": "Arrival",
                    "airline": "Airline",
                    "flight_number": "FlightNo",
                    "cabin_class": "FlightClassCode",
                    "price": "__total__",
                    "currency": "Currency",
                },
            }
        ),
        adapter_key="generic",
        timeout_seconds=90,
        max_retries=0,
    ),
    ProviderCreate(
        name="United Solutions · Reservation",
        slug="us-reserve",
        description="SOAP Reservation (hold + PNR). Pass flight_id from us-search.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.FLIGHT_RESERVATION,
        base_url=US_ENDPOINT_DEFAULT,
        endpoint_path="",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config=_us_auth(
            {
                "operation": "Reservation",
                "response_mode": "data",
                "fields": {
                    "strFlightId": "$payload.flight_id",
                    "strReturnFlightId": "$payload.return_flight_id|optional",
                },
                "result_map": {
                    "pnr": "PNRNO",
                    "reservation_status": "ReservationStatus",
                    "airline_id": "AirlineID",
                    "flight_id": "FlightId",
                    "ttl_date": "TTLDate",
                    "ttl_time": "TTLTime",
                },
            }
        ),
        adapter_key="generic",
        timeout_seconds=90,
        max_retries=0,
    ),
    ProviderCreate(
        name="United Solutions · Issue ticket",
        slug="us-ticket",
        description="SOAP IssueTicket. Requires contact + flight_id.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.ISSUE_TICKET,
        base_url=US_ENDPOINT_DEFAULT,
        endpoint_path="",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config=_us_auth(
            {
                "operation": "IssueTicket",
                "response_mode": "data",
                "fields": {
                    "strFlightId": "$payload.flight_id",
                    "strReturnFlightId": "$payload.return_flight_id|optional",
                    "strContactName": "$payload.contact_name",
                    "strContactEmail": "$payload.contact_email",
                    "strContactMobile": "$payload.contact_mobile",
                    "strInvoiceParty": "$payload.contact_name",
                    "strPanNo": "",
                },
                "result_map": {
                    "pnr": "PnrNo",
                    "ticket_nos": "TicketNo",
                    "airline": "Airline",
                },
            }
        ),
        adapter_key="generic",
        timeout_seconds=90,
        max_retries=0,
    ),
    ProviderCreate(
        name="United Solutions · Balance",
        slug="us-balance",
        description="SOAP CheckBalance.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.AGENCY_BALANCE,
        base_url=US_ENDPOINT_DEFAULT,
        endpoint_path="",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config=_us_auth(
            {
                "operation": "CheckBalance",
                "response_mode": "data",
                "fields": {
                    "strUserId": "$auth.user_id",
                    "strPassword": "$auth.password",
                    "strAgencyId": "$auth.agency_id",
                    "strAirlineId": "$payload.airline_id|upper|optional",
                    "strClientIP": "$auth.client_ip",
                },
            }
        ),
        adapter_key="generic",
        timeout_seconds=60,
        max_retries=0,
    ),
    ProviderCreate(
        name="United Solutions · Itinerary",
        slug="us-itinerary",
        description="SOAP GetItinerary.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.GET_ITINERARY,
        base_url=US_ENDPOINT_DEFAULT,
        endpoint_path="",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config=_us_auth(
            {
                "operation": "GetItinerary",
                "response_mode": "data",
                "fields": {
                    "strUserId": "$auth.user_id",
                    "strPassword": "$auth.password",
                    "strAgencyId": "$auth.agency_id",
                    "strPnrNo": "$payload.pnr|upper|optional",
                    "strTicketNo": "$payload.ticket_no|optional",
                    "strClientIP": "$auth.client_ip",
                },
            }
        ),
        adapter_key="generic",
        timeout_seconds=60,
        max_retries=0,
    ),
    ProviderCreate(
        name="United Solutions · Flight detail",
        slug="us-flight-detail",
        description="SOAP GetFlightDetail.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.FLIGHT_DETAIL,
        base_url=US_ENDPOINT_DEFAULT,
        endpoint_path="",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config=_us_auth(
            {
                "operation": "GetFlightDetail",
                "response_mode": "data",
                "fields": {
                    "strUserId": "$auth.user_id",
                    "strPassword": "$auth.password",
                    "strAgencyId": "$auth.agency_id",
                    "strFlightId": "$payload.flight_id",
                    "strClientIP": "$auth.client_ip",
                },
            }
        ),
        adapter_key="generic",
        timeout_seconds=60,
        max_retries=0,
    ),
    ProviderCreate(
        name="United Solutions · Sales report",
        slug="us-sales",
        description="SOAP SalesReport.",
        enabled=True,
        provider_kind=ProviderKind.AGENCY,
        api_type=ApiType.SALES_REPORT,
        base_url=US_ENDPOINT_DEFAULT,
        endpoint_path="",
        http_method=HttpMethod.POST,
        auth_type=AuthType.BASIC,
        auth_config=_us_auth(
            {
                "operation": "SalesReport",
                "response_mode": "data",
                "fields": {
                    "strUserId": "$auth.user_id",
                    "strPassword": "$auth.password",
                    "strAgencyId": "$auth.agency_id",
                    "strFromDate": "$payload.from_date|api_date",
                    "strToDate": "$payload.to_date|api_date",
                    "strClientIP": "$auth.client_ip",
                },
            }
        ),
        adapter_key="generic",
        timeout_seconds=90,
        max_retries=0,
    ),
]


async def _ensure_sqlite_columns(connection) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    result = await connection.execute(text("PRAGMA table_info(providers)"))
    rows = result.fetchall()
    if rows:
        existing = {row[1] for row in rows}
        if "provider_kind" not in existing:
            await connection.execute(
                text(
                    "ALTER TABLE providers ADD COLUMN provider_kind VARCHAR(32) "
                    "DEFAULT 'airline' NOT NULL"
                )
            )
        if "api_type" not in existing:
            await connection.execute(
                text(
                    "ALTER TABLE providers ADD COLUMN api_type VARCHAR(32) "
                    "DEFAULT 'flight_search' NOT NULL"
                )
            )

    users_info = await connection.execute(text("PRAGMA table_info(users)"))
    user_cols = {row[1] for row in users_info.fetchall()}
    if user_cols:
        if "role" not in user_cols:
            await connection.execute(
                text("ALTER TABLE users ADD COLUMN role VARCHAR(32) DEFAULT 'admin' NOT NULL")
            )
            await connection.execute(
                text("UPDATE users SET role = 'admin' WHERE is_admin = 1")
            )
            await connection.execute(
                text("UPDATE users SET role = 'b2b' WHERE is_admin = 0")
            )
        if "description" not in user_cols:
            await connection.execute(text("ALTER TABLE users ADD COLUMN description TEXT"))
        await connection.execute(text("UPDATE users SET role = 'b2b' WHERE role = 'operator'"))

    keys_info = await connection.execute(text("PRAGMA table_info(api_keys)"))
    key_cols = {row[1] for row in keys_info.fetchall()}
    if key_cols and "key_secret" not in key_cols:
        await connection.execute(text("ALTER TABLE api_keys ADD COLUMN key_secret TEXT"))


async def _normalize_provider_classifications(connection) -> None:
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


def _is_united_solutions(provider: Provider) -> bool:
    slug = provider.slug or ""
    if slug.startswith("us-"):
        return True
    cfg = provider.auth_config if isinstance(provider.auth_config, dict) else {}
    soap = cfg.get("soap") if isinstance(cfg.get("soap"), dict) else {}
    return str(soap.get("namespace") or "") == US_SOAP_NS


async def _prune_non_us_providers(session) -> None:
    """Keep only United Solutions providers."""
    result = await session.execute(select(Provider))
    removed = 0
    for provider in list(result.scalars().all()):
        if _is_united_solutions(provider):
            continue
        await session.delete(provider)
        removed += 1
    if removed:
        logger.info("Removed %s non–United Solutions provider(s)", removed)


async def _sync_united_solutions(session) -> None:
    """Apply US_* env credentials and ensure soap templates on us-* rows."""
    result = await session.execute(select(Provider))
    providers = list(result.scalars().all())
    seed_by_slug = {p.slug: p for p in DEMO_PROVIDERS}

    us_ready = bool(
        (settings.us_user_id or "").strip()
        and (settings.us_password or "").strip()
        and (settings.us_agency_id or "").strip()
    )
    endpoint = (settings.us_endpoint or "").strip() or US_ENDPOINT_DEFAULT
    touched = 0
    for provider in providers:
        if not _is_united_solutions(provider):
            continue
        cfg = provider.auth_config if isinstance(provider.auth_config, dict) else {}
        soap = cfg.get("soap") if isinstance(cfg.get("soap"), dict) else None
        if not soap and provider.slug in seed_by_slug:
            seed_cfg = seed_by_slug[provider.slug].auth_config or {}
            soap = seed_cfg.get("soap") if isinstance(seed_cfg.get("soap"), dict) else None

        merged = dict(cfg)
        if us_ready:
            merged.update(
                {
                    "user_id": settings.us_user_id.strip(),
                    "password": settings.us_password.strip(),
                    "agency_id": settings.us_agency_id.strip(),
                    "client_ip": (settings.us_client_ip or settings.us_user_id).strip(),
                    "endpoint": endpoint,
                }
            )
        if soap:
            merged["soap"] = soap
        provider.auth_config = merged
        provider.base_url = endpoint
        provider.adapter_key = "generic"
        provider.timeout_seconds = float(settings.us_timeout_seconds or 90)
        if us_ready and settings.us_auto_enable:
            provider.enabled = True
        touched += 1
    if touched and us_ready:
        logger.info(
            "Synced United Solutions credentials onto %s provider(s)%s",
            touched,
            " (enabled)" if settings.us_auto_enable else "",
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

        await AuthSettingsRepository(session).ensure_defaults()

        await _prune_non_us_providers(session)
        await session.flush()

        result = await session.execute(select(Provider))
        existing = list(result.scalars().all())
        slugs = {p.slug for p in existing}
        if not existing:
            for demo in DEMO_PROVIDERS:
                session.add(Provider(**demo.model_dump()))
            logger.info("Seeded %s United Solutions providers", len(DEMO_PROVIDERS))
        else:
            for demo in DEMO_PROVIDERS:
                if demo.slug not in slugs:
                    session.add(Provider(**demo.model_dump()))
                    logger.info("Seeded United Solutions provider: %s", demo.slug)

        await session.flush()
        await _sync_united_solutions(session)
        await session.commit()
