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

Typical agency flow: **sectors → availability → reserve (hold) → issue ticket → itinerary**.

### United Solutions (only configured provider)

This install seeds **United Solutions only** (`us-*` rows). Each uses `adapter_key=generic` +
**dynamic SOAP mapping** in `auth_config.soap` (not `request_mapping` / `response_mapping` — those stay `{}`).

Credentials from `.env` sync on startup:

```env
US_ENDPOINT=http://dev.usbooking.org/us/UnitedSolutions
US_USER_ID=TSTAPI
US_PASSWORD=PASSWORD
US_AGENCY_ID=PLZ178
US_AUTO_ENABLE=true
```

| Slug | API type | SOAP op |
|------|----------|---------|
| `us-sectors` | `sector_codes` | `SectorCode` |
| `us-search` | `flight_search` | `FlightAvailability` |
| `us-reserve` | `flight_reservation` | `Reservation` |
| `us-ticket` | `issue_ticket` | `IssueTicket` |
| `us-balance` | `agency_balance` | `CheckBalance` |
| `us-itinerary` | `get_itinerary` | `GetItinerary` |
| `us-flight-detail` | `flight_detail` | `GetFlightDetail` |
| `us-sales` | `sales_report` | `SalesReport` |

#### Admin UI — dynamic mapping form (preferred)

Open http://localhost:8000/admin → **Providers** → **Add provider** or **Edit** on a `us-*` row.
This opens a **full-page form** (not a side drawer).

Under **Dynamic field mapping**:

1. **SOAP / United Solutions style mapping** is checked for all `us-*` providers.
2. Fill SOAP meta: **operation**, **response mode** (`offers` for search, `data` for booking), **items tag**, **wrap tags**, **namespace**.
3. Edit the **Request mapping** table (add/remove rows as needed):

| Form column | What you set | Example (`us-search`) |
|-------------|--------------|------------------------|
| SOAP tag | Partner XML body element | `strSectorFrom` |
| Source | `our request ($payload)` / `credential ($auth)` / `constant` | our request |
| Our / auth field | Unified API or credential key | `origin` |
| Transforms | optional `upper`, `api_date`, `str`, `optional` | `upper` |

4. Edit the **Response mapping** table:

| Form column | What you set | Example (`us-search`) |
|-------------|--------------|------------------------|
| Our API field | `NormalizedOffer` or `data.*` key | `offer_id` |
| Partner XML tag | SOAP tag (or `__total__` for fare sum) | `FlightId` |

5. Click **Save** — the form writes `auth_config.soap` (`fields`, `item_map` / `result_map`, …).  
   REST request/response map boxes stay `{}` for SOAP providers.  
   Raw JSON is still available under **Advanced — raw JSON** if you need it.

#### Seeded `us-search` mapping (what the form shows)

**Request** (our API / auth → SOAP)

| SOAP tag | Source | Our / auth field | Transforms |
|----------|--------|------------------|------------|
| `strUserId` | credential | `user_id` | — |
| `strPassword` | credential | `password` | — |
| `strAgencyId` | credential | `agency_id` | — |
| `strSectorFrom` | our request | `origin` | `upper` |
| `strSectorTo` | our request | `destination` | `upper` |
| `strFlightDate` | our request | `departure_date` | `api_date` |
| `strReturnDate` | our request | `return_date` | `api_date`, `optional` |
| `intAdult` | our request | `adults` | `str` |
| `strTripType` | constant | `O` | — |
| `strNationality` | constant | `NP` | — |
| `strClientIP` | credential | `client_ip` | — |

**Response** (`response mode = offers` → `NormalizedOffer`)

| Our API field | Partner XML tag |
|---------------|-----------------|
| `offer_id` | `FlightId` (use as `flight_id` on reserve) |
| `origin` | `Departure` |
| `destination` | `Arrival` |
| `airline` | `Airline` |
| `flight_number` | `FlightNo` |
| `cabin_class` | `FlightClassCode` |
| `price` | `__total__` (AdultFare + FuelSurcharge + Tax + AdultVAT) |
| `currency` | `Currency` |

Items come from wrap tags `Outbound,Inbound` + items tag `Availability`.

#### Other seeded `us-*` ops (same form)

| Slug | Response mode | Request highlights | Response highlights |
|------|---------------|--------------------|---------------------|
| `us-sectors` | `data` | `strUserId` ← auth `user_id` | auto `sectors[]` from items tag `Sector` |
| `us-reserve` | `data` | `strFlightId` ← `flight_id` | `pnr`←`PNRNO`, `reservation_status`←`ReservationStatus`, … |
| `us-ticket` | `data` | `flight_id` + contact fields | `pnr`←`PnrNo`, `ticket_nos`←`TicketNo` |
| `us-balance` | `data` | auth + optional `airline_id` | raw SOAP payload |
| `us-itinerary` | `data` | auth + optional `pnr` / `ticket_no` | raw SOAP payload |
| `us-flight-detail` | `data` | auth + `flight_id` | raw SOAP payload |
| `us-sales` | `data` | auth + `from_date` / `to_date` (`api_date`) | raw SOAP payload |

Change mappings in the Admin form (or seeds in `app/bootstrap.py`), **Save**, then **Test connection** / call the aggregate route.

```bash
curl -s http://127.0.0.1:8000/api/v1/flights/search \
  -H 'Content-Type: application/json' \
  -d '{"origin":"KTM","destination":"PKR","departure_date":"2026-09-15","adults":1}'

curl -s http://127.0.0.1:8000/api/v1/booking/reserve \
  -H 'Content-Type: application/json' \
  -d '{"flight_id":"<FlightId from search>"}'
```

Non–United Solutions providers are removed on startup.

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

## Adding a new provider (step by step)

Prefer **config-only** onboarding with `adapter_key=generic`. Write a custom adapter only when the provider needs non-standard flows (multi-step login, HTML scraping, custom XML, etc.).

> **Note (this install):** startup currently **prunes every provider that is not United Solutions** (`us-*` / SOAP namespace `http://booking.us.org/`). To keep a new provider across restarts, either add it to `DEMO_PROVIDERS` in `app/bootstrap.py`, or remove/disable `_prune_non_us_providers` in that file.

### Step 1 — Pick the operation (`api_type`)

One provider row = **one** booking operation. If the partner exposes search + reserve + ticket, create **three** rows (different slugs), each with its own `api_type`.

| Your goal | Set `api_type` to | Our aggregate API |
|-----------|-------------------|-------------------|
| List airports / sectors | `sector_codes` | `GET /api/v1/booking/sectors` |
| Check agency credit | `agency_balance` | `POST /api/v1/booking/balance` |
| Search availability | `flight_search` | `POST /api/v1/flights/search` |
| Hold / create PNR | `flight_reservation` | `POST /api/v1/booking/reserve` |
| Issue ticket | `issue_ticket` | `POST /api/v1/booking/ticket` |
| Fetch itinerary | `get_itinerary` | `POST /api/v1/booking/itinerary` |
| Flight / fare detail | `flight_detail` | `POST /api/v1/booking/flight-detail` |
| PNR lookup | `pnr_detail` | `POST /api/v1/booking/pnr` |
| Sales report | `sales_report` | `POST /api/v1/booking/sales-report` |

Also set **provider kind**:

- `airline` — direct carrier API
- `agency` — ticket booking / B2B agency API

Aggregation only calls **enabled** providers whose `api_type` matches the route. Confirm wiring under Admin → **Aggregation map**.

### Step 2 — Know our unified API model

Clients always talk to **our** fields. The adapter maps those to the partner’s fields.

#### Search request (`FlightSearchRequest`)

| Our field | Meaning |
|-----------|---------|
| `origin` | Origin IATA (e.g. `KTM`) |
| `destination` | Destination IATA (e.g. `PKR`) |
| `departure_date` | `YYYY-MM-DD` |
| `return_date` | optional `YYYY-MM-DD` |
| `adults` | passenger count |
| `cabin_class` | `economy` / `business` / … |
| `currency` | e.g. `NPR` |
| `extras` | free-form dict merged into the partner payload |

#### Search offer (`NormalizedOffer`) — **must map for `flight_search`**

| Our field | Meaning | Required? |
|-----------|---------|-----------|
| `provider` | filled automatically from slug | auto |
| `offer_id` | partner fare / flight id used later to reserve | **yes** |
| `origin` / `destination` | sector | recommended |
| `airline` | carrier code | recommended |
| `flight_number` | e.g. `U4601` | recommended |
| `cabin_class` | fare / class code | recommended |
| `price` | total as number | recommended |
| `currency` | e.g. `NPR` | recommended |
| `departure_at` / `arrival_at` | ISO or partner datetime | optional |
| `stops` / `duration_minutes` | optional | optional |
| `raw` | full partner row kept for debugging | auto when available |

#### Booking / agency payloads (common keys)

| Operation | Our request fields (high level) | Typical success data |
|-----------|----------------------------------|----------------------|
| `flight_reservation` | `flight_id` (= search `offer_id`), optional contact / passengers | `pnr`, `reservation_status`, `ttl_date` |
| `issue_ticket` | `flight_id`, `contact_name`, `contact_email`, `contact_mobile`, `passengers` | `pnr`, `ticket_nos` |
| `get_itinerary` | `pnr` and/or `ticket_no` | itinerary payload |
| `flight_detail` | `flight_id` | detail payload |
| `agency_balance` | optional `airline_id` | balance payload |
| `sector_codes` | (none) | `sectors: [{sector_code, sector_name}]` |
| `sales_report` | `from_date`, `to_date` | report payload |

Schemas live in `app/schemas/aggregation.py` — treat that file as the source of truth.

### Step 3 — Create the provider row

**Admin UI:** open http://localhost:8000/admin → Providers → **Add provider** (full-page form, not a modal).

**Or API:**

```bash
TOKEN=$(curl -s http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | jq -r .access_token)

curl -s http://localhost:8000/api/v1/admin/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Partner Air Search",
    "slug": "partner-air-search",
    "description": "Partner REST availability",
    "enabled": false,
    "provider_kind": "airline",
    "api_type": "flight_search",
    "base_url": "https://api.partner-air.example",
    "endpoint_path": "/v1/search",
    "http_method": "POST",
    "auth_type": "api_key",
    "auth_config": {"api_key": "secret", "header_name": "X-API-Key"},
    "adapter_key": "generic",
    "timeout_seconds": 30,
    "max_retries": 1,
    "request_mapping": {},
    "response_mapping": {}
  }'
```

Fill these first, then continue to **Dynamic field mapping** (Step 4):

| Field | What to set |
|-------|-------------|
| `name` / `slug` | Unique display name and URL-safe slug |
| `provider_kind` / `api_type` | From Step 1 |
| `base_url` + `endpoint_path` | Partner host + path (joined automatically) |
| `http_method` | Usually `POST` |
| `auth_type` + credentials | Auth dropdown + Advanced → Auth config JSON |
| `adapter_key` | `generic` (default) |
| `enabled` | leave `false` until mapping + Test pass |

### Step 4 — Map fields in the Admin form (our model ↔ partner)

In the provider editor, use **Dynamic field mapping**. Everything is row-based and editable; **Save** persists it.

#### A) REST JSON providers (SOAP checkbox **off**)

**Request mapping** table — each row:

| Our API field | Partner field / path |
|---------------|----------------------|
| `origin` | `from` |
| `destination` | `to` |
| `departure_date` | `journey.date` |
| `adults` | `pax.adults` |

**Response mapping** table — each row:

| Our API field | Partner field / path |
|---------------|----------------------|
| `items` | `results` *(path to the offer array)* |
| `offer_id` | `id` |
| `price` | `total_fare` |
| `currency` | `currency` |
| `airline` | `carrier` |
| `flight_number` | `flightNo` |

Rules:

1. Map every partner field that must come from the client.
2. Use dotted partner paths for nested JSON (`journey.date`).
3. For search, `items` must point at the offer array; `offer_id` must be the id you later send as `flight_id` on reserve.
4. If request mapping is empty, the unified payload is passed through (minus `providers` / `extras`).
5. On Save, rows are written to `request_mapping` / `response_mapping` (also visible under Advanced JSON).

#### B) SOAP providers (SOAP checkbox **on** — United Solutions style)

Same idea, different columns. The form writes `auth_config.soap` (not REST map JSON).

**Meta fields in the form**

| Form field | Stored as | Example |
|------------|-----------|---------|
| SOAP operation | `soap.operation` | `FlightAvailability` |
| Response mode | `soap.response_mode` | `offers` (search) or `data` (booking) |
| Items tag | `soap.items_tag` | `Availability` |
| Wrap tags | `soap.wrap_tags` | `Outbound,Inbound` |
| Namespace | `soap.namespace` | `http://booking.us.org/` |

**Request mapping** table → `soap.fields`

| SOAP tag | Source | Our / auth field | Transforms | Becomes |
|----------|--------|------------------|------------|---------|
| `strSectorFrom` | our request | `origin` | `upper` | `$payload.origin\|upper` |
| `strFlightDate` | our request | `departure_date` | `api_date` | `$payload.departure_date\|api_date` |
| `strUserId` | credential | `user_id` | — | `$auth.user_id` |
| `strTripType` | constant | `O` | — | `O` |

Transforms available in the form: `upper`, `api_date`, `str`, `optional`.

**Response mapping** table

| Response mode | Stored as | Our API field | Partner XML tag |
|---------------|-----------|---------------|-----------------|
| `offers` | `soap.item_map` | `offer_id` | `FlightId` |
| `offers` | `soap.item_map` | `price` | `__total__` *(built-in fare sum)* |
| `data` | `soap.result_map` | `pnr` | `PNRNO` |

Use **+ Request field** / **+ Response field** to add rows; **×** to remove. Open a seeded `us-*` provider to see a complete working form.

### Step 5 — Verify mapping end-to-end

1. **Save** the provider from the form (enabled can stay off for Test).
2. Confirm Advanced JSON matches what you edited (SOAP → `auth_config.soap`; REST → request/response maps).
3. Click **Test connection** (or `POST /api/v1/admin/providers/{id}/test`).
   - Search should return `sample_normalized` with a real `offer_id`.
   - Ops that need `flight_id` / `pnr` will auth-probe if those ids are missing — that only proves credentials, not the full booking map.
4. **Enable** the provider.
5. Confirm Admin → **Aggregation map** shows it under the right `api_type`.
6. Call the aggregate route:

```bash
# Search
curl -s http://127.0.0.1:8000/api/v1/flights/search \
  -H 'Content-Type: application/json' \
  -d '{
    "origin": "KTM",
    "destination": "PKR",
    "departure_date": "2026-09-15",
    "adults": 1,
    "providers": ["partner-air-search"]
  }' | jq '.offers[0]'

# Reserve using offer_id from search
curl -s http://127.0.0.1:8000/api/v1/booking/reserve \
  -H 'Content-Type: application/json' \
  -d '{
    "flight_id": "<offer_id from search>",
    "providers": ["partner-air-reserve"]
  }' | jq '.results[0]'
```

7. Confirm:
   - `providers_succeeded >= 1`
   - search `offers[].offer_id` is non-empty
   - reserve/ticket `results[].data` contains the keys you care about (`pnr`, …)
   - failures on one provider do not zero out the whole aggregate response

### Step 6 — Persist the provider (optional but recommended)

Admin-created rows are stored in the DB, but **this install deletes non–United Solutions rows on startup**. To make a provider permanent:

1. Copy the working config into a `ProviderCreate(...)` entry in `DEMO_PROVIDERS` (`app/bootstrap.py`), **or**
2. Stop pruning by removing the `await _prune_non_us_providers(session)` call in `init_db()`.

Reload the app and confirm the slug still appears in Admin → Providers.

### Custom adapter (only when config is not enough)

Use this when one HTTP/SOAP call + mappings cannot express the partner flow.

1. Create `app/adapters/my_provider.py` implementing `ProviderAdapter` (`execute`, optionally `test_connectivity`).
2. In `execute`, accept the unified payload, call the partner, and return:
   - search: `AdapterResponse(success=True, offers=[NormalizedOffer(...), ...])`
   - other ops: `AdapterResponse(success=True, data={...})`
3. Register in `app/adapters/__init__.py`:

```python
from app.adapters.my_provider import MyProviderAdapter
register_adapter("my_provider", MyProviderAdapter)
# or add to _REGISTRY: "my_provider": MyProviderAdapter
```

4. Set the provider row’s `adapter_key` to `my_provider`.
5. Re-run Step 5.

### Mapping cheat sheet

| What you want | Admin form | Saved into |
|---------------|------------|------------|
| REST: our request → partner JSON | Dynamic field mapping (SOAP off) → Request table | `request_mapping` |
| REST: partner JSON → our offers | Response table (`items` + field rows) | `response_mapping` |
| SOAP: our request / auth → XML body | SOAP on → Request table (tag / source / field / transforms) | `auth_config.soap.fields` |
| SOAP: XML → `NormalizedOffer` | Response mode **offers** → Response table | `auth_config.soap.item_map` |
| SOAP: XML → booking `data` | Response mode **data** → Response table | `auth_config.soap.result_map` |
| Credentials / API keys | Auth type + Auth config (Advanced JSON) | `auth_config` |

### Auth config examples

| Type | `auth_config` |
|------|----------------|
| API Key | `{"api_key":"...","header_name":"X-API-Key"}` or `{"api_key":"...","location":"query","query_param":"api_key"}` |
| Bearer | `{"token":"..."}` |
| Basic | `{"username":"...","password":"..."}` |
| OAuth2 | `{"token_url":"https://.../token","client_id":"...","client_secret":"...","scope":"..."}` |
| Custom headers | `{"headers":{"X-Partner-Id":"...","X-Signature":"..."}}` |
| SOAP (US-style) | credentials + nested `"soap": { "namespace", "operation", "fields", "item_map" / "result_map", ... }` |

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
