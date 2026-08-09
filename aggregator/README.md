# API Aggregation Platform

Scalable FastAPI platform for **Nepal domestic airline & ticket booking**. It exposes a **single REST API** while integrating multiple airline and ticket-agency providers. Each provider is handled by an **adapter** responsible for authentication, request transformation, API calls, and response normalization.

Scope is flights only — airlines and ticket booking agencies (not hotels or other verticals). Provider failures are isolated. **Search and booking results are not stored**; the platform only proxies, aggregates, and normalizes live responses.

## Features

- Concurrent multi-provider aggregation with per-provider error isolation
- Adapter pattern + SOLID layout; new providers via admin config (generic HTTP) or a small custom adapter class
- Admin APIs + lightweight admin UI for provider CRUD, enable/disable, auth, headers, mappings, connectivity tests
- Auth types: API Key, Bearer, OAuth2 client credentials, Basic, Custom Headers
- Request/response field mapping (dotted paths)
- Retries + timeouts (tenacity + httpx)
- JWT auth for admin endpoints
- Automatic OpenAPI/Swagger at `/docs`
- Docker + docker-compose (Postgres)

## Project layout

```
app/
  adapters/          # Adapter pattern (base, generic HTTP, auth strategies, mapping, mocks)
  api/v1/            # REST routers (auth, admin providers, aggregation)
  core/              # Security, logging, exceptions
  models/            # SQLAlchemy models
  repositories/      # Data access
  schemas/           # Pydantic request/response models
  services/          # Aggregation + provider application services
  static/admin.html  # Simple admin panel
  bootstrap.py       # DB init + seed data
  config.py          # Settings (pydantic-settings)
  database.py
  main.py
```

## Quick start (local)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # already present for local demo
uvicorn app.main:app --reload --port 8000
```

Open:

- Swagger UI: http://localhost:8000/docs
- Admin panel: http://localhost:8000/admin
- Health: http://localhost:8000/health

Default admin: `admin` / `admin123`

The admin **Dashboard** shows live API metrics (request volume, success rate, latency charts). Metrics are in-memory only — search/booking payloads are never stored.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

API: http://localhost:8000

## Core flows

### Nepal domestic booking APIs

Each booking operation maps to an `api_type` and an aggregate route. Home in the admin UI has a playground for all of them.

| Operation | API type | Aggregate endpoint |
|-----------|----------|--------------------|
| Sector codes | `sector_codes` | `GET /api/v1/booking/sectors` |
| Agency balance | `agency_balance` | `POST /api/v1/booking/balance` |
| Flight availability | `flight_search` | `POST /api/v1/flights/search` |
| Reservation (hold) | `flight_reservation` | `POST /api/v1/booking/reserve` |
| Issue ticket | `issue_ticket` | `POST /api/v1/booking/ticket` |
| Get itinerary | `get_itinerary` | `POST /api/v1/booking/itinerary` |
| Flight detail | `flight_detail` | `POST /api/v1/booking/flight-detail` |
| PNR maintenance | `pnr_detail` | `POST /api/v1/booking/pnr` |
| Sales report | `sales_report` | `POST /api/v1/booking/sales-report` |

Typical agency flow: **sectors → availability → reserve (hold) → issue ticket → itinerary/PNR**.

### Mock aggregate results (demo)

On first startup the app seeds **Nepal domestic airline** and **agency booking** mocks. No external API keys required.

| Provider | Slug | Adapter | API type |
|----------|------|---------|----------|
| Buddha Air (U4) | `buddha-air` | `mock_buddha_air` | `flight_search` |
| Yeti Airlines (YT) | `yeti-airlines` | `mock_yeti_airlines` | `flight_search` |
| Shree Airlines (N9) | `shree-airlines` | `mock_shree_airlines` | `flight_search` |
| Nepal · Sector codes | `nepal-sectors` | `mock_nepal_booking` | `sector_codes` |
| Nepal · Agency balance | `nepal-balance` | `mock_nepal_booking` | `agency_balance` |
| Nepal · Reservation | `nepal-reserve` | `mock_nepal_booking` | `flight_reservation` |
| Nepal · Issue ticket | `nepal-ticket` | `mock_nepal_booking` | `issue_ticket` |
| Nepal · Get itinerary | `nepal-itinerary` | `mock_nepal_booking` | `get_itinerary` |
| Nepal · Flight detail | `nepal-flight-detail` | `mock_nepal_booking` | `flight_detail` |
| Nepal · PNR maintenance | `nepal-pnr` | `mock_nepal_booking` | `pnr_detail` |
| Nepal · Sales report | `nepal-sales` | `mock_nepal_booking` | `sales_report` |

Try availability on **KTM → PKR**:

```bash
curl -s http://127.0.0.1:8000/api/v1/flights/search \
  -H 'Content-Type: application/json' \
  -d '{
    "origin": "KTM",
    "destination": "PKR",
    "departure_date": "2026-09-15",
    "adults": 1,
    "currency": "NPR"
  }'
```

Other useful demo airports: `BIR`, `BWA`, `BHR`, `KEP`, `BDP`, `DHI`.

```bash
# Sectors
curl -s http://127.0.0.1:8000/api/v1/booking/sectors

# Balance
curl -s http://127.0.0.1:8000/api/v1/booking/balance \
  -H 'Content-Type: application/json' -d '{"airline_id":"U4"}'

# Hold (use offer_id / flight_id from search)
curl -s http://127.0.0.1:8000/api/v1/booking/reserve \
  -H 'Content-Type: application/json' \
  -d '{"flight_id":"U4-demo"}'
```

Optional: limit providers with `"providers": ["buddha-air"]` on search, or `"providers": ["nepal-reserve"]` on booking ops.

Other seeded rows (`nepal-travel-agency`, `example-http`, `example-booking`) are **disabled** templates — enable only after configuring real URLs/auth.

### Aggregate flight search

Without `providers`, all **enabled** providers with `api_type=flight_search` are queried.

### Admin login

```bash
TOKEN=$(curl -s http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | jq -r .access_token)
```

### Manage providers

```bash
# List
curl -s http://localhost:8000/api/v1/admin/providers \
  -H "Authorization: Bearer $TOKEN"

# Create (generic HTTP provider — no code change)
curl -s http://localhost:8000/api/v1/admin/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Partner Air",
    "slug": "partner-air",
    "base_url": "https://api.partner-air.example",
    "endpoint_path": "/v1/search",
    "http_method": "POST",
    "auth_type": "api_key",
    "auth_config": {"api_key": "secret", "header_name": "X-API-Key"},
    "request_mapping": {
      "origin": "from",
      "destination": "to",
      "departure_date": "date",
      "adults": "adults"
    },
    "response_mapping": {
      "items": "results",
      "offer_id": "id",
      "price": "total_fare",
      "currency": "currency",
      "origin": "origin",
      "destination": "destination"
    },
    "adapter_key": "generic",
    "enabled": true
  }'

# Enable / disable / test
curl -s -X POST http://localhost:8000/api/v1/admin/providers/1/enable \
  -H "Authorization: Bearer $TOKEN"
curl -s -X POST http://localhost:8000/api/v1/admin/providers/1/test \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{}'
```

## Provider classification

Each provider has two type fields (set in admin, no code change):

| Field | Purpose | Examples |
|-------|---------|----------|
| **Provider kind** | Who they are | `airline`, `agency` (ticket booking agency) |
| **API type** | Ticket-booking operation | `flight_search`, `flight_reservation`, `issue_ticket`, `sector_codes`, … |

Aggregation routes only call **enabled** providers matching the route's API type (see booking table above). In the admin UI, **Home** tries each op; **Aggregation map** shows which providers are wired per type.

Admin APIs:

- `GET /api/v1/admin/providers/types` — catalog of kinds + API types
- `GET /api/v1/admin/providers/aggregation-map` — participants per API type
- `GET /api/v1/admin/providers?api_type=flight_search&provider_kind=airline` — filtered list

## Adding a new provider

### Config-only (preferred)

1. Open `/admin` or call `POST /api/v1/admin/providers`
2. Set `base_url`, `endpoint_path`, `auth_*`, `request_mapping`, `response_mapping`
3. Keep `adapter_key` as `generic`
4. Enable and run connectivity test

### Custom adapter (special logic)

1. Implement `ProviderAdapter` in `app/adapters/`
2. Register it in `app/adapters/__init__.py` via `register_adapter("my_key", MyAdapter)`
3. Set the provider's `adapter_key` to `my_key` in admin

Seeded demo adapters: `mock_buddha_air`, `mock_yeti_airlines`, `mock_shree_airlines`, `mock_nepal_booking` (Nepal domestic mocks, no external network).

## Auth config examples

| Type | `auth_config` |
|------|----------------|
| API Key | `{"api_key":"...","header_name":"X-API-Key"}` or `{"api_key":"...","location":"query","query_param":"api_key"}` |
| Bearer | `{"token":"..."}` |
| Basic | `{"username":"...","password":"..."}` |
| OAuth2 | `{"token_url":"https://.../token","client_id":"...","client_secret":"...","scope":"..."}` |
| Custom headers | `{"headers":{"X-Partner-Id":"...","X-Signature":"..."}}` |

## Tests

```bash
pip install pytest pytest-asyncio
pytest -q
```

## Design notes

- **Single Responsibility**: routers → services → repositories → adapters
- **Open/Closed**: new providers via config or registered adapters without changing aggregation core
- **Dependency Inversion**: aggregation depends on `ProviderAdapter`, not concrete HTTP clients
- **No persistence of offers**: aggregation is live-only; only provider configuration and admin users are stored
