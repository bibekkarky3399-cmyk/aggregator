"""Repositories for API clients, keys, and auth settings."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.api_client import ApiClient, ApiKey, AuthSetting, ClientType
from app.services.api_key_service import hash_api_key, key_prefix_for_display, slugify, validate_scopes


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_AUTH_SETTINGS: dict[str, str] = {
    "require_api_key": "true",
    "admin_bypass_api_key": "true",
    "api_key_header": "X-API-Key",
    "api_key_prefix": "sk_live_",
    "default_scopes": '["*"]',
}


class AuthSettingsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_defaults(self) -> None:
        for key, value in DEFAULT_AUTH_SETTINGS.items():
            existing = await self.db.get(AuthSetting, key)
            if existing is None:
                self.db.add(AuthSetting(key=key, value=value))
        await self.db.flush()

    async def get_all(self) -> dict[str, str]:
        result = await self.db.execute(select(AuthSetting))
        rows = {r.key: r.value for r in result.scalars().all()}
        merged = {**DEFAULT_AUTH_SETTINGS, **rows}
        return merged

    async def get_bool(self, key: str, default: bool = False) -> bool:
        all_settings = await self.get_all()
        raw = (all_settings.get(key) or str(default)).strip().lower()
        return raw in {"1", "true", "yes", "on"}

    async def get_str(self, key: str, default: str = "") -> str:
        all_settings = await self.get_all()
        return (all_settings.get(key) or default).strip() or default

    async def update(self, patch: dict[str, str]) -> dict[str, str]:
        for key, value in patch.items():
            row = await self.db.get(AuthSetting, key)
            if row is None:
                self.db.add(AuthSetting(key=key, value=value))
            else:
                row.value = value
                row.updated_at = utcnow()
        await self.db.flush()
        return await self.get_all()


class ApiClientRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_clients(self, *, active_only: bool = False) -> list[ApiClient]:
        stmt = (
            select(ApiClient)
            .options(selectinload(ApiClient.keys))
            .order_by(ApiClient.created_at.desc())
        )
        if active_only:
            stmt = stmt.where(ApiClient.is_active.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().unique().all())

    async def get(self, client_id: int) -> ApiClient | None:
        result = await self.db.execute(
            select(ApiClient)
            .where(ApiClient.id == client_id)
            .options(selectinload(ApiClient.keys))
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> ApiClient | None:
        result = await self.db.execute(select(ApiClient).where(ApiClient.slug == slug))
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: int) -> ApiClient | None:
        result = await self.db.execute(
            select(ApiClient)
            .where(ApiClient.user_id == user_id)
            .options(selectinload(ApiClient.keys))
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        name: str,
        slug: str | None,
        client_type: ClientType,
        contact_email: str | None,
        notes: str | None,
        is_active: bool,
        user_id: int | None,
    ) -> ApiClient:
        base = slugify(slug or name)
        candidate = base
        n = 2
        while await self.get_by_slug(candidate):
            candidate = f"{base}-{n}"
            n += 1
        client = ApiClient(
            name=name,
            slug=candidate,
            client_type=client_type,
            contact_email=contact_email,
            notes=notes,
            is_active=is_active,
            user_id=user_id,
        )
        self.db.add(client)
        await self.db.flush()
        await self.db.refresh(client)
        return await self.get(client.id)  # type: ignore[return-value]

    async def update(self, client: ApiClient, **fields) -> ApiClient:
        for key, value in fields.items():
            if value is not None or key in {"contact_email", "notes", "user_id"}:
                setattr(client, key, value)
        client.updated_at = utcnow()
        await self.db.flush()
        return await self.get(client.id)  # type: ignore[return-value]

    async def delete(self, client: ApiClient) -> None:
        await self.db.delete(client)
        await self.db.flush()


class ApiKeyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, key_id: int) -> ApiKey | None:
        return await self.db.get(ApiKey, key_id)

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        result = await self.db.execute(
            select(ApiKey)
            .where(ApiKey.key_hash == key_hash)
            .options(selectinload(ApiKey.client))
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        client_id: int,
        name: str,
        raw_key: str,
        scopes: list[str],
        expires_at: datetime | None,
        created_by_user_id: int | None,
    ) -> ApiKey:
        row = ApiKey(
            client_id=client_id,
            name=name,
            key_prefix=key_prefix_for_display(raw_key),
            key_hash=hash_api_key(raw_key),
            key_secret=raw_key,
            scopes=validate_scopes(scopes),
            is_active=True,
            expires_at=expires_at,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def touch_last_used(self, key: ApiKey) -> None:
        key.last_used_at = utcnow()
        await self.db.flush()

    async def revoke(self, key: ApiKey) -> ApiKey:
        key.is_active = False
        key.revoked_at = utcnow()
        await self.db.flush()
        await self.db.refresh(key)
        return key

    async def set_secret(self, key: ApiKey, raw_key: str) -> ApiKey:
        raw = raw_key.strip()
        hashed = hash_api_key(raw)
        existing = await self.get_by_hash(hashed)
        if existing and existing.id != key.id:
            raise ValueError("This API key already exists")
        key.key_hash = hashed
        key.key_prefix = key_prefix_for_display(raw)
        key.key_secret = raw
        await self.db.flush()
        await self.db.refresh(key)
        return key

    async def update(self, key: ApiKey, **fields) -> ApiKey:
        for k, v in fields.items():
            if k == "scopes" and v is not None:
                setattr(key, k, validate_scopes(v))
            elif v is not None or k in {"expires_at"}:
                setattr(key, k, v)
        await self.db.flush()
        await self.db.refresh(key)
        return key
