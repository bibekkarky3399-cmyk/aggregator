"""Utilities for nested dict path get/set and request/response mapping."""

from __future__ import annotations

from typing import Any


def get_by_path(data: Any, path: str, default: Any = None) -> Any:
    """Resolve a dotted path like 'data.flights.0.price' against nested dicts/lists."""
    if not path:
        return data
    current = data
    for part in path.split("."):
        if current is None:
            return default
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return default
        else:
            return default
    return current


def set_by_path(data: dict[str, Any], path: str, value: Any) -> None:
    """Set a value at a dotted path, creating intermediate dicts as needed."""
    parts = path.split(".")
    current: dict[str, Any] = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def apply_request_mapping(
    unified: dict[str, Any],
    mapping: dict[str, str],
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Transform a unified request into a provider-specific payload.

    mapping keys are unified field names (or dotted paths into unified),
    mapping values are provider field paths.
    Unmapped extras under 'extras' are merged last if present.
    """
    result: dict[str, Any] = {}
    if defaults:
        result.update(defaults)

    for source_key, target_path in (mapping or {}).items():
        value = get_by_path(unified, source_key)
        if value is not None:
            set_by_path(result, target_path, value)

    # If no mapping configured, pass through the unified payload (minus control fields)
    if not mapping:
        passthrough = {
            k: v
            for k, v in unified.items()
            if k not in {"providers", "extras"} and v is not None
        }
        result = {**result, **passthrough}

    extras = unified.get("extras") or {}
    if isinstance(extras, dict):
        for key, value in extras.items():
            if key not in result:
                result[key] = value

    return result


def extract_items(raw: Any, items_path: str | None) -> list[Any]:
    """Extract a list of items from a raw provider response using items_path."""
    if not items_path:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            for candidate in ("data", "results", "items", "offers", "flights"):
                value = raw.get(candidate)
                if isinstance(value, list):
                    return value
            return [raw]
        return []

    value = get_by_path(raw, items_path)
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def normalize_item(
    item: Any,
    field_mapping: dict[str, str],
    provider_slug: str,
) -> dict[str, Any]:
    """
    Map a single provider item into the unified offer shape.

    field_mapping maps unified field names -> provider item paths.
    Special key 'items' is ignored here (used only for list extraction).
    """
    if not isinstance(item, dict):
        return {
            "provider": provider_slug,
            "offer_id": None,
            "raw": {"value": item},
        }

    normalized: dict[str, Any] = {"provider": provider_slug}
    mapping = {k: v for k, v in (field_mapping or {}).items() if k != "items"}

    if mapping:
        for unified_field, provider_path in mapping.items():
            normalized[unified_field] = get_by_path(item, provider_path)
        normalized["raw"] = item
    else:
        # Best-effort passthrough for unmapped providers
        aliases = {
            "offer_id": ["id", "offer_id", "offerId", "flight_id"],
            "origin": ["origin", "from", "departure_airport", "departureAirport"],
            "destination": ["destination", "to", "arrival_airport", "arrivalAirport"],
            "departure_at": ["departure_at", "departure", "departureTime", "depart_at"],
            "arrival_at": ["arrival_at", "arrival", "arrivalTime", "arrive_at"],
            "airline": ["airline", "carrier", "airline_code", "airlineCode"],
            "flight_number": ["flight_number", "flightNumber", "flight_no"],
            "cabin_class": ["cabin_class", "cabin", "cabinClass", "class"],
            "price": ["price", "total", "fare", "amount", "total_price"],
            "currency": ["currency", "currency_code", "currencyCode"],
            "stops": ["stops", "stop_count", "numberOfStops"],
            "duration_minutes": ["duration_minutes", "duration", "durationMinutes"],
        }
        for field, keys in aliases.items():
            for key in keys:
                if key in item and item[key] is not None:
                    value = item[key]
                    if field == "price" and isinstance(value, dict):
                        value = value.get("total") or value.get("amount") or value.get("value")
                    normalized[field] = value
                    break
        normalized["raw"] = item

    # Coerce price to float when possible
    if "price" in normalized and normalized["price"] is not None:
        try:
            normalized["price"] = float(normalized["price"])
        except (TypeError, ValueError):
            pass

    return normalized


def normalize_response(
    raw: Any,
    response_mapping: dict[str, str],
    provider_slug: str,
) -> list[dict[str, Any]]:
    items_path = (response_mapping or {}).get("items")
    items = extract_items(raw, items_path)
    return [normalize_item(item, response_mapping or {}, provider_slug) for item in items]
