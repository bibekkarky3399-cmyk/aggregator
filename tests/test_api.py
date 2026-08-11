import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

US_SLUGS = {
    "us-sectors",
    "us-search",
    "us-reserve",
    "us-ticket",
    "us-balance",
    "us-itinerary",
    "us-flight-detail",
    "us-sales",
}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac


@pytest.mark.asyncio
async def test_health(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_login_and_us_providers_only(client):
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    providers = await client.get("/api/v1/admin/providers", headers=headers)
    assert providers.status_code == 200
    rows = providers.json()
    slugs = {p["slug"] for p in rows}
    assert slugs == US_SLUGS
    assert all(p.get("adapter_key") == "generic" for p in rows)
    assert all(p.get("enabled") for p in rows)

    catalog = await client.get("/api/v1/admin/providers/types", headers=headers)
    assert catalog.status_code == 200
    body = catalog.json()
    assert any(k["value"] == "airline" for k in body["provider_kinds"])
    assert any(a["value"] == "flight_search" for a in body["api_types"])

    agg_map = await client.get("/api/v1/admin/providers/aggregation-map", headers=headers)
    assert agg_map.status_code == 200
    flight_search = next(e for e in agg_map.json()["entries"] if e["api_type"] == "flight_search")
    assert flight_search["enabled_count"] == 1
    assert {p["slug"] for p in flight_search["providers"]} == {"us-search"}


@pytest.mark.asyncio
async def test_booking_api_group_map(client):
    """United Solutions booking ops are wired in the aggregation map."""
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    agg_map = await client.get("/api/v1/admin/providers/aggregation-map", headers=headers)
    assert agg_map.status_code == 200
    types = {e["api_type"] for e in agg_map.json()["entries"] if e["enabled_count"] > 0}
    assert "sector_codes" in types
    assert "flight_search" in types
    assert "flight_reservation" in types
    assert "issue_ticket" in types
    assert "agency_balance" in types
    assert "get_itinerary" in types
    assert "flight_detail" in types
    assert "sales_report" in types
