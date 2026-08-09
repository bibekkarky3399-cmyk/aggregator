"""
Mock adapters for Nepal domestic airlines (demo only — not live airline APIs).

Carriers modeled after publicly known domestic operators:
- Buddha Air (U4)
- Yeti Airlines (YT)
- Shree Airlines (N9)

Common domestic airports: KTM, PKR, BIR, BWA, BHR, KEP, BDP, DHI, JKR, SIF.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

from app.adapters.base import AdapterRequest, AdapterResponse, ProviderAdapter
from app.schemas.aggregation import NormalizedOffer

# Approximate block times (minutes) for popular Nepal domestic sectors
_SECTOR_MINUTES: dict[tuple[str, str], int] = {
    ("KTM", "PKR"): 25,
    ("PKR", "KTM"): 25,
    ("KTM", "BIR"): 40,
    ("BIR", "KTM"): 40,
    ("KTM", "BWA"): 35,
    ("BWA", "KTM"): 35,
    ("KTM", "BHR"): 20,
    ("BHR", "KTM"): 20,
    ("KTM", "KEP"): 55,
    ("KEP", "KTM"): 55,
    ("KTM", "BDP"): 55,
    ("BDP", "KTM"): 55,
    ("KTM", "DHI"): 65,
    ("DHI", "KTM"): 65,
    ("KTM", "JKR"): 30,
    ("JKR", "KTM"): 30,
    ("KTM", "SIF"): 15,
    ("SIF", "KTM"): 15,
}


def _duration(origin: str, destination: str, fallback: int = 35) -> int:
    return _SECTOR_MINUTES.get((origin, destination), fallback)


def _add_minutes(date: str, hhmm: str, add: int) -> str:
    """Return ISO-like local datetime string date + time + minutes."""
    hours, minutes = map(int, hhmm.split(":"))
    total = hours * 60 + minutes + add
    hh, mm = divmod(total % (24 * 60), 60)
    return f"{date}T{hh:02d}:{mm:02d}:00"


def _digest(*parts: Any) -> str:
    return hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()


class _NepalDomesticMockAdapter(ProviderAdapter):
    """Shared mock behavior for Nepal domestic carriers."""

    airline_code: str = "XX"
    airline_name: str = "Mock Airline"
    fare_families: tuple[str, ...] = ("Saver", "Flex")
    base_fare_npr: int = 4500
    fare_spread: int = 2500
    schedule: tuple[str, ...] = ("07:30", "12:15", "16:45")
    latency_s: float = 0.05

    async def execute(self, request: AdapterRequest) -> AdapterResponse:
        started = time.perf_counter()
        await asyncio.sleep(self.latency_s)
        op = (request.operation or "flight_search").lower()
        if op in {"search", "flight_search", "connectivity"}:
            return self._availability(request.payload, started)
        if op == "sector_codes":
            return self._ok(started, self._sectors())
        if op == "agency_balance":
            return self._ok(started, self._balance(request.payload))
        if op == "flight_reservation":
            return self._ok(started, self._reservation(request.payload))
        if op == "issue_ticket":
            return self._ok(started, self._issue_ticket(request.payload))
        if op == "get_itinerary":
            return self._ok(started, self._itinerary(request.payload))
        if op == "flight_detail":
            return self._ok(started, self._flight_detail(request.payload))
        if op == "pnr_detail":
            return self._ok(started, self._pnr_detail(request.payload))
        if op == "sales_report":
            return self._ok(started, self._sales_report(request.payload))
        return AdapterResponse(
            success=False,
            error=f"Unsupported operation: {op}",
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _ok(self, started: float, data: Any) -> AdapterResponse:
        return AdapterResponse(
            success=True,
            data=data,
            raw=data,
            latency_ms=(time.perf_counter() - started) * 1000,
            status_code=200,
        )

    def _sectors(self) -> dict[str, Any]:
        sectors = [
            {"sector_code": "KTM", "sector_name": "KATHMANDU"},
            {"sector_code": "PKR", "sector_name": "POKHARA"},
            {"sector_code": "BIR", "sector_name": "BIRATNAGAR"},
            {"sector_code": "BWA", "sector_name": "BHAIRAHAWA"},
            {"sector_code": "BHR", "sector_name": "BHARATPUR"},
            {"sector_code": "KEP", "sector_name": "NEPALGUNJ"},
            {"sector_code": "BDP", "sector_name": "BHADRAPUR"},
            {"sector_code": "DHI", "sector_name": "DHANGADHI"},
            {"sector_code": "JKR", "sector_name": "JANAKPUR"},
            {"sector_code": "SIF", "sector_name": "SIMARA"},
        ]
        return {"airline": self.airline_code, "sectors": sectors}

    def _balance(self, payload: dict[str, Any]) -> dict[str, Any]:
        airline = payload.get("airline_id") or self.airline_code
        digest = _digest(self.provider.slug, airline, "balance")
        amount = 50000 + (int(digest[:6], 16) % 900000)
        return {
            "airline_id": airline,
            "airline_name": self.airline_name,
            "agency_name": "NEPAL DEMO AGENCY",
            "balance_amount": round(amount / 100, 2),
            "currency": "NPR",
        }

    def _reservation(self, payload: dict[str, Any]) -> dict[str, Any]:
        flight_id = payload.get("flight_id") or "unknown"
        digest = _digest(self.airline_code, flight_id, "pnr")
        pnr = "".join(chr(65 + int(digest[i], 16) % 26) for i in range(6))
        return {
            "airline_id": self.airline_code,
            "flight_id": flight_id,
            "return_flight_id": payload.get("return_flight_id"),
            "pnr": pnr,
            "reservation_status": "HK",
            "ttl_date": "15-SEP-2026",
            "ttl_time": "12:20",
            "hold_minutes": 15,
        }

    def _issue_ticket(self, payload: dict[str, Any]) -> dict[str, Any]:
        flight_id = payload.get("flight_id") or "unknown"
        digest = _digest(self.airline_code, flight_id, "tkt")
        pnr = "".join(chr(65 + int(digest[i], 16) % 26) for i in range(6))
        ticket = f"999{int(digest[:10], 16) % 10**10:010d}"
        pax = (payload.get("passengers") or [{"first_name": "DEMO", "last_name": "PAX"}])[0]
        return {
            "airline": self.airline_code,
            "pnr": pnr,
            "ticket_no": ticket,
            "passenger": pax,
            "contact_name": payload.get("contact_name"),
            "flight_id": flight_id,
            "currency": "NPR",
            "status": "ISSUED",
        }

    def _itinerary(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "pnr": payload.get("pnr") or "DEMO01",
            "ticket_no": payload.get("ticket_no"),
            "airline_id": payload.get("airline_id") or self.airline_code,
            "sector": "KTM-PKR",
            "status": "CONFIRMED",
            "passengers": [{"name": "DEMO PAX", "type": "ADULT"}],
        }

    def _flight_detail(self, payload: dict[str, Any]) -> dict[str, Any]:
        flight_id = payload.get("flight_id") or "unknown"
        return {
            "flight_id": flight_id,
            "airline": self.airline_code,
            "airline_name": self.airline_name,
            "aircraft_type": "ATR72",
            "free_baggage": "20 + 5 KG",
        }

    def _pnr_detail(self, payload: dict[str, Any]) -> dict[str, Any]:
        pnr = payload.get("pnr") or "DEMO01"
        return {
            "pnr": pnr,
            "airline_id": self.airline_code,
            "maintenance_url": f"https://mock.pnr.local/{self.airline_code}/{pnr}",
            "actions": ["reschedule", "cancel"],
        }

    def _sales_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "airline_id": self.airline_code,
            "from_date": payload.get("from_date"),
            "to_date": payload.get("to_date"),
            "tickets_issued": 12,
            "gross_sales_npr": 184500.0,
            "commission_npr": 9200.0,
        }

    def _availability(self, payload: dict[str, Any], started: float) -> AdapterResponse:
        origin = str(payload.get("origin", "KTM")).upper()
        destination = str(payload.get("destination", "PKR")).upper()
        date = str(payload.get("departure_date", "2026-09-15"))
        adults = int(payload.get("adults") or 1)
        cabin = str(payload.get("cabin_class", "economy"))
        currency = str(payload.get("currency") or "NPR")

        duration = _duration(origin, destination)
        digest = _digest(self.airline_code, origin, destination, date, self.provider.slug)
        offers: list[NormalizedOffer] = []

        for idx, depart in enumerate(self.schedule[:2]):
            fare_family = self.fare_families[idx % len(self.fare_families)]
            jitter = int(digest[idx * 4 : idx * 4 + 4], 16) % self.fare_spread
            price = round(self.base_fare_npr + jitter + (adults - 1) * 800 + idx * 350, 2)
            flight_no = f"{self.airline_code}{100 + (int(digest[8 + idx : 11 + idx], 16) % 80)}"
            flight_id = f"{self.airline_code}-{digest[idx * 6 : idx * 6 + 12]}"

            offers.append(
                NormalizedOffer(
                    provider=self.provider.slug,
                    offer_id=flight_id,
                    origin=origin,
                    destination=destination,
                    departure_at=f"{date}T{depart}:00",
                    arrival_at=_add_minutes(date, depart, duration),
                    airline=self.airline_code,
                    flight_number=flight_no,
                    cabin_class=cabin,
                    price=price,
                    currency=currency,
                    stops=0,
                    duration_minutes=duration,
                    raw={
                        "source": f"mock-{self.provider.slug}",
                        "airline_name": self.airline_name,
                        "fare_family": fare_family,
                        "flight_id": flight_id,
                        "sector": f"{origin}-{destination}",
                        "tax": 250,
                        "fuel_surcharge": 0,
                        "free_baggage": "20 + 5 KG",
                        "refundable": fare_family.lower().startswith("flex"),
                        "country": "NP",
                        "market": "nepal_domestic",
                    },
                )
            )

        return AdapterResponse(
            success=True,
            offers=offers,
            data={"flights": [o.model_dump() for o in offers]},
            latency_ms=(time.perf_counter() - started) * 1000,
            status_code=200,
            raw={"flights": [o.model_dump() for o in offers]},
        )

    async def test_connectivity(self, sample_payload: dict[str, Any] | None = None) -> AdapterResponse:
        return await self.execute(
            AdapterRequest(
                payload=sample_payload
                or {
                    "origin": "KTM",
                    "destination": "PKR",
                    "departure_date": "2026-09-15",
                    "adults": 1,
                    "currency": "NPR",
                },
                operation="connectivity",
            )
        )


class MockBuddhaAirAdapter(_NepalDomesticMockAdapter):
    """Mock Buddha Air (U4) — major Nepal domestic/regional carrier."""

    airline_code = "U4"
    airline_name = "Buddha Air"
    fare_families = ("Value", "Flex")
    base_fare_npr = 4200
    fare_spread = 2200
    schedule = ("07:15", "11:40", "15:55")
    latency_s = 0.05


class MockYetiAirlinesAdapter(_NepalDomesticMockAdapter):
    """Mock Yeti Airlines (YT) — major Nepal domestic carrier."""

    airline_code = "YT"
    airline_name = "Yeti Airlines"
    fare_families = ("Eco", "Flexi")
    base_fare_npr = 4500
    fare_spread = 2400
    schedule = ("08:00", "13:20", "17:10")
    latency_s = 0.07


class MockShreeAirlinesAdapter(_NepalDomesticMockAdapter):
    """Mock Shree Airlines (N9) — Nepal domestic carrier."""

    airline_code = "N9"
    airline_name = "Shree Airlines"
    fare_families = ("Standard", "Flex")
    base_fare_npr = 4800
    fare_spread = 2000
    schedule = ("09:05", "14:30")
    latency_s = 0.06


class MockNepalBookingAdapter(_NepalDomesticMockAdapter):
    """
    Mock Nepal domestic B2B booking API.

    Covers sectors, balance, reservation, ticketing, itinerary, flight detail,
    PNR maintenance, and sales report for the Nepal domestic market.
    """

    airline_code = "NP"
    airline_name = "Nepal Booking"
    fare_families = ("Economy", "Flex")
    base_fare_npr = 4300
    schedule = ("08:30", "14:00")
    latency_s = 0.04

    def _balance(self, payload: dict[str, Any]) -> dict[str, Any]:
        airline = payload.get("airline_id")
        carriers = [
            ("U4", "BUDDHA AIR"),
            ("YT", "YETI AIRLINES"),
            ("N9", "SHREE AIRLINES"),
            ("S1", "SAURYA AIRLINES"),
        ]
        if airline:
            carriers = [c for c in carriers if c[0] == str(airline).upper()] or [
                (str(airline).upper(), str(airline).upper())
            ]
        rows = []
        for code, name in carriers:
            digest = _digest("np", code, "bal")
            rows.append(
                {
                    "airline_id": code,
                    "airline_name": name,
                    "agency_name": "NEPAL DEMO AGENCY",
                    "balance_amount": round((40000 + int(digest[:5], 16) % 800000) / 100, 2),
                    "currency": "NPR",
                }
            )
        return {"balances": rows}


# Backwards-compatible aliases (older seed data / docs may still reference these keys)
MockSkyWingsAdapter = MockBuddhaAirAdapter
MockAeroLinkAdapter = MockYetiAirlinesAdapter
MockUnitedSolutionsAdapter = MockNepalBookingAdapter
