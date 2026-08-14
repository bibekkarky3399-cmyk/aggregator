from __future__ import annotations

import json
from datetime import timezone

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import get_subject_from_token
from app.database import get_db
from app.models.provider import ApiType
from app.models.user import User
from app.repositories.api_client_repository import AuthSettingsRepository, ApiKeyRepository
from app.repositories.user_repository import UserRepository
from app.services.api_key_service import ApiPrincipal, hash_api_key, scopes_allow, utcnow

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Missing bearer token")

    try:
        username = get_subject_from_token(credentials.credentials)
    except Exception as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    user = await UserRepository(db).get_by_username(username)
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user


def _extract_api_key(
    *,
    header_name: str,
    x_api_key: str | None,
    authorization: str | None,
    request: Request,
) -> str | None:
    # Preferred configurable header (default X-API-Key)
    custom = request.headers.get(header_name) or request.headers.get(header_name.lower())
    if custom:
        return custom.strip()
    if x_api_key:
        return x_api_key.strip()
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() in {"apikey", "api-key"}:
            return parts[1].strip()
    # Query fallback for simple integrations
    q = request.query_params.get("api_key")
    return q.strip() if q else None


async def _try_admin_bypass(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> User | None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        username = get_subject_from_token(credentials.credentials)
    except Exception:
        return None
    user = await UserRepository(db).get_by_username(username)
    if user and user.is_active and user.is_admin:
        return user
    return None


def require_api_access(api_type: ApiType):
    """
    Protect a public aggregator endpoint.

    Resolution order:
    1. If require_api_key is off → allow anonymous (dev)
    2. Else if admin_bypass and valid admin JWT → allow
    3. Else require a valid active API key with matching scope
    """

    async def _dependency(
        request: Request,
        db: AsyncSession = Depends(get_db),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        authorization: str | None = Header(default=None),
    ) -> ApiPrincipal:
        settings_repo = AuthSettingsRepository(db)
        require_key = await settings_repo.get_bool("require_api_key", True)
        admin_bypass = await settings_repo.get_bool("admin_bypass_api_key", True)
        header_name = await settings_repo.get_str("api_key_header", "X-API-Key")

        if not require_key:
            return ApiPrincipal(kind="open")

        if admin_bypass:
            admin = await _try_admin_bypass(credentials, db)
            if admin:
                return ApiPrincipal(kind="admin", user=admin)

        raw = _extract_api_key(
            header_name=header_name,
            x_api_key=x_api_key,
            authorization=authorization,
            request=request,
        )
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Missing API key. Pass it via {header_name} header.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        key = await ApiKeyRepository(db).get_by_hash(hash_api_key(raw))
        if (
            key is None
            or not key.is_active
            or key.revoked_at is not None
            or (key.client and not key.client.is_active)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive API key",
            )
        if key.expires_at is not None:
            exp = key.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < utcnow():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key expired",
                )
        if not scopes_allow(key.scopes or [], api_type):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key is not scoped for '{api_type.value}'",
            )

        await ApiKeyRepository(db).touch_last_used(key)
        return ApiPrincipal(kind="api_key", client=key.client, api_key=key)

    return _dependency


async def get_auth_settings_payload(db: AsyncSession) -> dict:
    raw = await AuthSettingsRepository(db).get_all()
    try:
        default_scopes = json.loads(raw.get("default_scopes") or '["*"]')
    except json.JSONDecodeError:
        default_scopes = ["*"]
    return {
        "require_api_key": (raw.get("require_api_key") or "true").lower() in {"1", "true", "yes", "on"},
        "admin_bypass_api_key": (raw.get("admin_bypass_api_key") or "true").lower()
        in {"1", "true", "yes", "on"},
        "api_key_header": raw.get("api_key_header") or "X-API-Key",
        "api_key_prefix": raw.get("api_key_prefix") or "sk_live_",
        "default_scopes": default_scopes if isinstance(default_scopes, list) else ["*"],
    }
