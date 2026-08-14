"""Schemas for API clients, keys, and auth settings."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


class ApiClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=100)
    client_type: Literal["b2b", "b2c", "internal", "system"] = "b2b"
    contact_email: EmailStr | None = None
    notes: str | None = None
    is_active: bool = True
    user_id: int | None = None
    # Issue a per-client API key in the same request
    issue_key: bool = True
    key_name: str = Field(default="Default", min_length=1, max_length=120)
    key_mode: Literal["auto", "manual"] = "auto"
    api_key: str | None = Field(default=None, min_length=24, max_length=200)
    # API map types this key may call. Required when issue_key is true.
    scopes: list[str] = Field(default_factory=list)


class ApiClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    client_type: Literal["b2b", "b2c", "internal", "system"] | None = None
    contact_email: EmailStr | None = None
    notes: str | None = None
    is_active: bool | None = None
    user_id: int | None = None


class ApiKeySummary(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class ApiClientResponse(BaseModel):
    id: int
    name: str
    slug: str
    client_type: str
    contact_email: str | None
    notes: str | None
    is_active: bool
    user_id: int | None
    created_at: datetime
    updated_at: datetime
    keys: list[ApiKeySummary] = []
    issued_api_key: str | None = None
    issued_api_key_message: str | None = None

    model_config = {"from_attributes": True}


class ApiKeyCreate(BaseModel):
    """Create an API key — auto-generate or supply a manual secret."""

    name: str = Field(default="Default", min_length=1, max_length=120)
    mode: Literal["auto", "manual"] = "auto"
    # Required when mode=manual
    api_key: str | None = Field(default=None, min_length=24, max_length=200)
    # API map types this key may call (or ["*"] for all)
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None

    @field_validator("api_key")
    @classmethod
    def strip_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if " " in cleaned:
            raise ValueError("API key must not contain spaces")
        return cleaned


class ApiKeyCreateResponse(BaseModel):
    """Returned once — includes the raw secret. Store it securely."""

    id: int
    client_id: int
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    expires_at: datetime | None
    created_at: datetime
    api_key: str
    message: str = "Copy this API key now. It will not be shown again."


class ApiKeyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    scopes: list[str] | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None


class AuthSettingsResponse(BaseModel):
    require_api_key: bool = True
    admin_bypass_api_key: bool = True
    api_key_header: str = "X-API-Key"
    api_key_prefix: str = "sk_live_"
    default_scopes: list[str] = Field(default_factory=lambda: ["*"])


class AuthSettingsUpdate(BaseModel):
    require_api_key: bool | None = None
    admin_bypass_api_key: bool | None = None
    api_key_header: str | None = Field(default=None, min_length=3, max_length=64)
    api_key_prefix: str | None = Field(default=None, min_length=3, max_length=24)
    default_scopes: list[str] | None = None


class SystemUserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str | None = Field(default=None, min_length=6, max_length=128)
    role: Literal["admin", "b2b", "b2c"] = "b2b"
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    is_admin: bool = False
    key_mode: Literal["auto", "manual"] = "auto"
    api_key: str | None = Field(default=None, min_length=8, max_length=200)
    scopes: list[str] = Field(default_factory=lambda: ["*"])

    @model_validator(mode="after")
    def role_credentials(self):
        if self.role == "admin":
            if not (self.password or "").strip():
                raise PydanticCustomError(
                    "missing",
                    "Password is required for admin users",
                )
            return self
        if self.key_mode == "manual" and not (self.api_key or "").strip():
            raise PydanticCustomError(
                "missing",
                "API key is required for B2B and B2C users",
            )
        if not self.scopes:
            raise PydanticCustomError(
                "missing",
                "Select at least one API for B2B and B2C users",
            )
        return self


class SystemUserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)
    role: Literal["admin", "b2b", "b2c"] | None = None
    description: str | None = Field(default=None, max_length=2000)
    is_admin: bool | None = None
    is_active: bool | None = None


class SystemUserKeyUpsert(BaseModel):
    key_mode: Literal["auto", "manual"] = "manual"
    api_key: str | None = Field(default=None, min_length=8, max_length=200)
    scopes: list[str] = Field(default_factory=lambda: ["*"])


class SystemUserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool
    is_admin: bool
    role: str = "b2b"
    description: str | None = None
    created_at: datetime
    linked_client_id: int | None = None
    api_key_id: int | None = None
    api_key: str | None = None
    api_key_prefix: str | None = None
    api_key_scopes: list[str] | None = None
    issued_api_key: str | None = None
    issued_api_key_message: str | None = None

    model_config = {"from_attributes": True}


class SystemUserListResponse(BaseModel):
    items: list[SystemUserResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ScopeCatalogItem(BaseModel):
    value: str
    label: str
    endpoint: str
    group: str


class ScopeCatalogResponse(BaseModel):
    scopes: list[ScopeCatalogItem]
