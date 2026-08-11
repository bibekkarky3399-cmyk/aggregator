from app.adapters.mapping import (
    apply_request_mapping,
    get_by_path,
    normalize_response,
    set_by_path,
)


def test_get_and_set_by_path():
    data = {"a": {"b": [{"c": 1}]}}
    assert get_by_path(data, "a.b.0.c") == 1
    assert get_by_path(data, "a.missing", default="x") == "x"

    out: dict = {}
    set_by_path(out, "departureAirport", "JFK")
    set_by_path(out, "passengers.adults", 2)
    assert out == {"departureAirport": "JFK", "passengers": {"adults": 2}}


def test_apply_request_mapping():
    unified = {
        "origin": "JFK",
        "destination": "LHR",
        "adults": 2,
        "providers": ["x"],
        "extras": {"promo": "SPRING"},
    }
    mapped = apply_request_mapping(
        unified,
        {"origin": "from", "destination": "to", "adults": "pax"},
        {"currency": "USD"},
    )
    assert mapped == {"currency": "USD", "from": "JFK", "to": "LHR", "pax": 2, "promo": "SPRING"}


def test_normalize_response():
    raw = {
        "data": {
            "offers": [
                {
                    "id": "o1",
                    "itinerary": {"origin": "JFK", "destination": "LHR", "stops": 0},
                    "price": {"total": "199.50", "currency": "USD"},
                }
            ]
        }
    }
    mapping = {
        "items": "data.offers",
        "offer_id": "id",
        "origin": "itinerary.origin",
        "destination": "itinerary.destination",
        "price": "price.total",
        "currency": "price.currency",
        "stops": "itinerary.stops",
    }
    offers = normalize_response(raw, mapping, "example")
    assert len(offers) == 1
    assert offers[0]["provider"] == "example"
    assert offers[0]["offer_id"] == "o1"
    assert offers[0]["price"] == 199.5
    assert offers[0]["origin"] == "JFK"
