"""Auth settings + system user management for the aggregation console."""

from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_settings_payload, get_current_admin
from app.core.exceptions import NotFoundError
from app.core.security import hash_password
from app.database import get_db
from app.models.api_client import ApiClient, ApiKey, ClientType
from app.models.user import User
from app.repositories.api_client_repository import ApiClientRepository, ApiKeyRepository, AuthSettingsRepository
from app.repositories.user_repository import UserRepository
from app.schemas.api_client import (
    AuthSettingsResponse,
    AuthSettingsUpdate,
    ScopeCatalogResponse,
    SystemUserCreate,
    SystemUserKeyUpsert,
    SystemUserListResponse,
    SystemUserResponse,
    SystemUserUpdate,
)
from app.services.api_key_service import generate_api_key, hash_api_key, key_prefix_for_display, scope_catalog

router = APIRouter(prefix="/admin/auth", tags=["Admin - Auth settings"])


@router.get("/settings", response_model=AuthSettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AuthSettingsResponse:
    payload = await get_auth_settings_payload(db)
    return AuthSettingsResponse(**payload)


@router.put("/settings", response_model=AuthSettingsResponse)
async def update_settings(
    body: AuthSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AuthSettingsResponse:
    patch: dict[str, str] = {}
    data = body.model_dump(exclude_unset=True)
    if "require_api_key" in data:
        patch["require_api_key"] = "true" if data["require_api_key"] else "false"
    if "admin_bypass_api_key" in data:
        patch["admin_bypass_api_key"] = "true" if data["admin_bypass_api_key"] else "false"
    if "api_key_header" in data and data["api_key_header"]:
        patch["api_key_header"] = data["api_key_header"].strip()
    if "api_key_prefix" in data and data["api_key_prefix"]:
        patch["api_key_prefix"] = data["api_key_prefix"].strip()
    if "default_scopes" in data and data["default_scopes"] is not None:
        patch["default_scopes"] = json.dumps(data["default_scopes"])
    if patch:
        await AuthSettingsRepository(db).update(patch)
    payload = await get_auth_settings_payload(db)
    return AuthSettingsResponse(**payload)


@router.get("/scopes", response_model=ScopeCatalogResponse)
async def list_scopes(_: User = Depends(get_current_admin)) -> ScopeCatalogResponse:
    return ScopeCatalogResponse(scopes=scope_catalog())  # type: ignore[arg-type]


def _role_client_type(role: str) -> ClientType:
    if role == "b2c":
        return ClientType.B2C
    if role == "admin":
        return ClientType.SYSTEM
    return ClientType.B2B


def _active_key(client: ApiClient | None) -> ApiKey | None:
    if not client:
        return None
    keys = [k for k in (client.keys or []) if k.is_active and not k.revoked_at]
    if not keys:
        return None
    return sorted(keys, key=lambda k: k.created_at, reverse=True)[0]


def _user_out(
    user: User,
    client: ApiClient | None = None,
    issued_api_key: str | None = None,
) -> SystemUserResponse:
    role = getattr(user, "role", None) or ("admin" if user.is_admin else "b2b")
    key = _active_key(client)
    secret = issued_api_key or (key.key_secret if key else None)
    prefix = key.key_prefix if key else None
    if secret and not prefix:
        prefix = key_prefix_for_display(secret)
    return SystemUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        role=role,
        description=getattr(user, "description", None),
        created_at=user.created_at,
        linked_client_id=client.id if client else None,
        api_key_id=key.id if key else None,
        api_key=secret,
        api_key_prefix=prefix,
        api_key_scopes=list(key.scopes or []) if key else (["*"] if secret else None),
        issued_api_key=issued_api_key,
        issued_api_key_message=None,
    )


async def _ensure_user_client(db: AsyncSession, user: User) -> ApiClient:
    repo = ApiClientRepository(db)
    client = await repo.get_by_user_id(user.id)
    if client:
        return client
    role = getattr(user, "role", None) or ("admin" if user.is_admin else "b2b")
    return await repo.create(
        name=f"{user.username} ({role})",
        slug=f"user-{user.username}",
        client_type=_role_client_type(role),
        contact_email=user.email,
        notes=user.description,
        is_active=user.is_active,
        user_id=user.id,
    )


async def _upsert_user_api_key(
    db: AsyncSession,
    user: User,
    *,
    created_by_user_id: int | None,
    key_mode: str = "auto",
    raw_or_none: str | None = None,
    scopes: list[str] | None = None,
) -> tuple[ApiClient, str]:
    client = await _ensure_user_client(db, user)
    key_repo = ApiKeyRepository(db)
    wanted_scopes = scopes if scopes is not None else ["*"]
    raw = (raw_or_none or "").strip() or None
    if key_mode == "manual" or raw:
        if not raw:
            raise HTTPException(status_code=400, detail="API key is required")
        if len(raw) < 8:
            raise HTTPException(status_code=400, detail="API key must be at least 8 characters")
    else:
        prefix = await AuthSettingsRepository(db).get_str("api_key_prefix", "sk_live_")
        raw = generate_api_key(prefix)

    active = _active_key(client)
    if active:
        if raw != (active.key_secret or ""):
            try:
                await key_repo.set_secret(active, raw)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        await key_repo.update(active, scopes=wanted_scopes)
        await db.refresh(client, attribute_names=["keys"])
        return client, raw

    existing = await key_repo.get_by_hash(hash_api_key(raw))
    if existing:
        raise HTTPException(status_code=409, detail="This API key already exists")
    await key_repo.create(
        client_id=client.id,
        name="Default",
        raw_key=raw,
        scopes=wanted_scopes,
        expires_at=None,
        created_by_user_id=created_by_user_id,
    )
    await db.refresh(client, attribute_names=["keys"])
    return client, raw


@router.get("/users", response_model=SystemUserListResponse)
async def list_system_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=8, ge=1, le=50),
    q: str | None = Query(default=None, max_length=120),
    role: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> SystemUserListResponse:
    repo = UserRepository(db)
    role_filter = role.strip().lower() if role else None
    if role_filter == "":
        role_filter = None
    if role_filter and role_filter not in {"admin", "b2b", "b2c"}:
        raise HTTPException(status_code=400, detail="Invalid role filter")
    total = await repo.count_users(q=q, role=role_filter)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages) if total else 1
    users = await repo.list_users(
        offset=(page - 1) * page_size,
        limit=page_size,
        q=q,
        role=role_filter,
    )
    client_repo = ApiClientRepository(db)
    items: list[SystemUserResponse] = []
    for u in users:
        linked = await client_repo.get_by_user_id(u.id)
        items.append(_user_out(u, linked))
    return SystemUserListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages if total else 0,
    )


@router.post("/users", response_model=SystemUserResponse, status_code=status.HTTP_201_CREATED)
async def create_system_user(
    body: SystemUserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> SystemUserResponse:
    repo = UserRepository(db)
    if await repo.get_by_username(body.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    role = body.role
    password = (body.password or "").strip()
    if role == "admin":
        if len(password) < 6:
            raise HTTPException(status_code=400, detail="Password is required for admin users")
    else:
        password = secrets.token_urlsafe(24)
    user = await repo.create_user(
        username=body.username,
        email=str(body.email),
        password=password,
        is_admin=role == "admin",
        is_active=body.is_active,
        role=role,
        description=(body.description or "").strip() or None,
    )
    if role == "admin":
        return _user_out(user)
    client, raw = await _upsert_user_api_key(
        db,
        user,
        created_by_user_id=admin.id,
        key_mode=body.key_mode,
        raw_or_none=body.api_key,
        scopes=body.scopes,
    )
    return _user_out(user, client, issued_api_key=raw)


@router.post("/users/{user_id}/api-key", response_model=SystemUserResponse)
async def upsert_system_user_api_key(
    user_id: int,
    body: SystemUserKeyUpsert,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> SystemUserResponse:
    user = await UserRepository(db).get_by_id(user_id)
    if not user:
        raise NotFoundError("User not found")
    role = getattr(user, "role", None) or ("admin" if user.is_admin else "b2b")
    if role == "admin":
        raise HTTPException(status_code=400, detail="Admin users do not use API keys")
    client, raw = await _upsert_user_api_key(
        db,
        user,
        created_by_user_id=admin.id,
        key_mode=body.key_mode,
        raw_or_none=body.api_key,
        scopes=body.scopes,
    )
    return _user_out(user, client, issued_api_key=raw)


@router.patch("/users/{user_id}", response_model=SystemUserResponse)
async def update_system_user(
    user_id: int,
    body: SystemUserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> SystemUserResponse:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotFoundError("User not found")
    data = body.model_dump(exclude_unset=True)
    if "password" in data and data["password"]:
        data["hashed_password"] = hash_password(data.pop("password"))
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"])
    if "role" in data and data["role"] is not None:
        data["is_admin"] = data["role"] == "admin"
    if "description" in data and data["description"] is not None:
        data["description"] = str(data["description"]).strip() or None
    if user.id == admin.id and data.get("is_admin") is False:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin flag")
    if user.id == admin.id and data.get("role") not in (None, "admin") and user.is_admin:
        raise HTTPException(status_code=400, detail="Cannot change your own admin role")
    if user.id == admin.id and data.get("is_active") is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    user = await repo.update_user(user, **data)
    client_repo = ApiClientRepository(db)
    linked = await client_repo.get_by_user_id(user.id)
    if linked and "is_active" in data:
        linked = await client_repo.update(linked, is_active=user.is_active)
    return _user_out(user, linked)
