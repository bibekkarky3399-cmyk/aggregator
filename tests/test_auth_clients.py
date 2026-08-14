import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac


async def _admin_headers(ac):
    login = await ac.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_b2b_user_api_key_scopes(client):
    headers = await _admin_headers(client)
    suffix = uuid.uuid4().hex[:8]
    key = f"sk_live_partner_{suffix}_abcdef12"
    res = await client.post(
        "/api/v1/admin/auth/users",
        headers=headers,
        json={
            "username": f"agency_{suffix}",
            "email": f"agency_{suffix}@example.com",
            "role": "b2b",
            "description": "Partner agency desk",
            "key_mode": "manual",
            "api_key": key,
            "scopes": ["flight_search", "sector_codes"],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["role"] == "b2b"
    assert body["api_key"] == key
    assert body["api_key_scopes"] == ["flight_search", "sector_codes"]

    denied = await client.get("/api/v1/booking/sectors")
    assert denied.status_code == 401

    ok_admin = await client.get("/api/v1/booking/sectors", headers=headers)
    assert ok_admin.status_code == 200

    ok_key = await client.get("/api/v1/booking/sectors", headers={"X-API-Key": key})
    assert ok_key.status_code == 200

    forbidden = await client.post(
        "/api/v1/booking/balance",
        headers={"X-API-Key": key},
        json={"airline_id": "U4"},
    )
    assert forbidden.status_code == 403

    blocked_login = await client.post(
        "/api/v1/auth/login",
        json={"username": f"agency_{suffix}", "password": "secret12"},
    )
    assert blocked_login.status_code == 401

    no_pw = await client.post(
        "/api/v1/admin/auth/users",
        headers=headers,
        json={
            "username": f"adm_{suffix}",
            "email": f"adm_{suffix}@example.com",
            "role": "admin",
        },
    )
    assert no_pw.status_code == 422

    admin_ok = await client.post(
        "/api/v1/admin/auth/users",
        headers=headers,
        json={
            "username": f"admok_{suffix}",
            "email": f"admok_{suffix}@example.com",
            "role": "admin",
            "password": "secret12",
        },
    )
    assert admin_ok.status_code == 201, admin_ok.text
    assert admin_ok.json()["api_key"] is None

    blocked_key = await client.post(
        f"/api/v1/admin/auth/users/{admin_ok.json()['id']}/api-key",
        headers=headers,
        json={"key_mode": "manual", "api_key": f"sk_live_admin_{suffix}_abcdefgh", "scopes": ["*"]},
    )
    assert blocked_key.status_code == 400


@pytest.mark.asyncio
async def test_b2c_manual_key_search(client):
    headers = await _admin_headers(client)
    suffix = uuid.uuid4().hex[:8]
    manual = f"sk_live_manual_{suffix}_abcdef1234567890"
    res = await client.post(
        "/api/v1/admin/auth/users",
        headers=headers,
        json={
            "username": f"app_{suffix}",
            "email": f"app_{suffix}@example.com",
            "role": "b2c",
            "key_mode": "manual",
            "api_key": manual,
            "scopes": ["*"],
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["role"] == "b2c"

    search = await client.post(
        "/api/v1/flights/search",
        headers={"X-API-Key": manual},
        json={"origin": "KTM", "destination": "PKR", "departure_date": "2026-09-01"},
    )
    assert search.status_code != 401


@pytest.mark.asyncio
async def test_edit_user_api_key(client):
    headers = await _admin_headers(client)
    suffix = uuid.uuid4().hex[:8]
    res = await client.post(
        "/api/v1/admin/auth/users",
        headers=headers,
        json={
            "username": f"ops_{suffix}",
            "email": f"ops_{suffix}@example.com",
            "role": "b2b",
            "key_mode": "manual",
            "api_key": f"sk_live_partner_{suffix}_abcdef12",
            "scopes": ["sector_codes"],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    listed = await client.get("/api/v1/admin/auth/users", headers=headers)
    match = next(u for u in listed.json()["items"] if u["id"] == body["id"])
    assert match["api_key"] == body["api_key"]

    rotated = await client.post(
        f"/api/v1/admin/auth/users/{body['id']}/api-key",
        headers=headers,
        json={
            "key_mode": "manual",
            "api_key": f"sk_live_rotated_{suffix}_xyz98765",
            "scopes": ["*"],
        },
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["api_key"] == f"sk_live_rotated_{suffix}_xyz98765"
    assert rotated.json()["api_key_scopes"] == ["*"]

    page = await client.get("/api/v1/admin/auth/users?page=1&page_size=1", headers=headers)
    assert page.status_code == 200
    body = page.json()
    assert "items" in body
    assert body["page"] == 1
    assert body["page_size"] == 1
    assert body["total"] >= 1
    assert len(body["items"]) == 1
