import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Ensure lifespan runs (DB init)
        async with app.router.lifespan_context(app):
            yield ac


@pytest.mark.asyncio
async def test_health(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_login_and_search(client):
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    providers = await client.get("/api/v1/admin/providers", headers=headers)
    assert providers.status_code == 200
    assert len(providers.json()) >= 2

    catalog = await client.get("/api/v1/admin/providers/types", headers=headers)
    assert catalog.status_code == 200
    body = catalog.json()
    assert any(k["value"] == "airline" for k in body["provider_kinds"])
    assert any(a["value"] == "flight_search" for a in body["api_types"])

    agg_map = await client.get("/api/v1/admin/providers/aggregation-map", headers=headers)
    assert agg_map.status_code == 200
    flight_search = next(e for e in agg_map.json()["entries"] if e["api_type"] == "flight_search")
    assert flight_search["enabled_count"] >= 2

    search = await client.post(
        "/api/v1/flights/search",
        json={
            "origin": "KTM",
            "destination": "PKR",
            "departure_date": "2026-09-15",
            "adults": 1,
            "currency": "NPR",
        },
    )
    assert search.status_code == 200
    body = search.json()
    assert body["providers_queried"] >= 2
    assert body["providers_succeeded"] >= 2
    assert body["total_offers"] >= 2
    assert all("provider" in o for o in body["offers"])
    assert any(o.get("currency") == "NPR" for o in body["offers"])
    assert any(o.get("airline") in {"U4", "YT", "N9"} for o in body["offers"])


@pytest.mark.asyncio
async def test_booking_api_group(client):
    """Nepal domestic booking ops aggregate across seeded agency providers."""
    sectors = await client.get("/api/v1/booking/sectors")
    assert sectors.status_code == 200
    sbody = sectors.json()
    assert sbody["operation"] == "sector_codes"
    assert sbody["providers_succeeded"] >= 1
    assert any(r.get("data", {}).get("sectors") for r in sbody["results"] if r.get("success"))

    balance = await client.post("/api/v1/booking/balance", json={"airline_id": "U4"})
    assert balance.status_code == 200
    assert balance.json()["providers_succeeded"] >= 1

    reserve = await client.post(
        "/api/v1/booking/reserve",
        json={"flight_id": "U4-testflight"},
    )
    assert reserve.status_code == 200
    rbody = reserve.json()
    assert rbody["providers_succeeded"] >= 1
    pnr = next(
        (r["data"]["pnr"] for r in rbody["results"] if r.get("success") and r.get("data")),
        None,
    )
    assert pnr

    ticket = await client.post(
        "/api/v1/booking/ticket",
        json={
            "flight_id": "U4-testflight",
            "contact_name": "Demo Agent",
            "contact_email": "agent@demo.np",
            "contact_mobile": "9800000000",
            "passengers": [{"first_name": "DEMO", "last_name": "PAX"}],
        },
    )
    assert ticket.status_code == 200
    assert ticket.json()["providers_succeeded"] >= 1

    itinerary = await client.post("/api/v1/booking/itinerary", json={"pnr": pnr})
    assert itinerary.status_code == 200
    assert itinerary.json()["providers_succeeded"] >= 1

    detail = await client.post(
        "/api/v1/booking/flight-detail",
        json={"flight_id": "U4-testflight"},
    )
    assert detail.status_code == 200
    assert detail.json()["providers_succeeded"] >= 1

    pnr_detail = await client.post("/api/v1/booking/pnr", json={"pnr": pnr})
    assert pnr_detail.status_code == 200
    assert pnr_detail.json()["providers_succeeded"] >= 1

    sales = await client.post(
        "/api/v1/booking/sales-report",
        json={"from_date": "2026-08-01", "to_date": "2026-08-31"},
    )
    assert sales.status_code == 200
    assert sales.json()["providers_succeeded"] >= 1

    agg_map = await client.get("/api/v1/admin/providers/aggregation-map")
    # aggregation-map requires auth — login first if needed
    if agg_map.status_code == 401:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        agg_map = await client.get("/api/v1/admin/providers/aggregation-map", headers=headers)
    assert agg_map.status_code == 200
    types = {e["api_type"] for e in agg_map.json()["entries"] if e["enabled_count"] > 0}
    assert "sector_codes" in types
    assert "flight_reservation" in types
    assert "issue_ticket" in types
