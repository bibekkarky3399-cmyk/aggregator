"""API key hashing, generation, and scope checks."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import get_settings
from app.models.api_client import ApiClient, ApiKey
from app.models.provider import API_TYPE_CATALOG, ApiType
from app.models.user import User

settings = get_settings()

SLUG_RE = re.compile(r"[^a-z0-9]+")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def slugify(value: str) -> str:
    s = SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return s[:90] or "client"


def hash_api_key(raw_key: str) -> str:
    """HMAC-SHA256 so keys are bound to the app secret."""
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        raw_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_api_key(prefix: str = "sk_live_") -> str:
    body = secrets.token_urlsafe(32)
    return f"{prefix}{body}"


def key_prefix_for_display(raw_key: str) -> str:
    if len(raw_key) <= 12:
        return raw_key
    return f"{raw_key[:12]}…"


def allowed_scope_values() -> set[str]:
    return {api_type.value for api_type in ApiType} | {"*"}


def normalize_scopes(scopes: list[str] | None) -> list[str]:
    """Keep '*' as full access. Empty list means no APIs (deny all)."""
    if not scopes:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for s in scopes:
        v = (s or "").strip()
        if not v or v in seen:
            continue
        if v == "*":
            return ["*"]
        seen.add(v)
        cleaned.append(v)
    return cleaned


def validate_scopes(scopes: list[str] | None) -> list[str]:
    """Scopes must be API-map types (or '*'). At least one is required."""
    normalized = normalize_scopes(scopes)
    if not normalized:
        raise ValueError("Select at least one API from the API map, or All APIs")
    allowed = allowed_scope_values()
    unknown = [s for s in normalized if s not in allowed]
    if unknown:
        raise ValueError(
            f"Unknown API scope(s): {', '.join(unknown)}. "
            "Use API map types such as flight_search, flight_reservation, issue_ticket."
        )
    return normalized


def scopes_allow(scopes: list[str], api_type: ApiType | str) -> bool:
    wanted = api_type.value if isinstance(api_type, ApiType) else str(api_type)
    if "*" in (scopes or []):
        return True
    return wanted in (scopes or [])


def scope_catalog() -> list[dict[str, str]]:
    items = []
    for api_type, meta in API_TYPE_CATALOG.items():
        items.append(
            {
                "value": api_type.value,
                "label": meta["label"],
                "endpoint": meta["aggregate_endpoint"],
                "group": meta.get("group", "other"),
            }
        )
    return items


@dataclass
class ApiPrincipal:
    """Resolved caller for a public API request."""

    kind: str  # "api_key" | "admin"
    client: ApiClient | None = None
    api_key: ApiKey | None = None
    user: User | None = None

    @property
    def display_name(self) -> str:
        if self.client:
            return self.client.name
        if self.user:
            return self.user.username
        return "unknown"
