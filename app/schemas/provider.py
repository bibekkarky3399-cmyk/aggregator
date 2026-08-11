from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.provider import (
    API_TYPE_CATALOG,
    PROVIDER_KIND_CATALOG,
    ApiType,
    AuthType,
    HttpMethod,
    ProviderKind,
)


class ProviderBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9\-]+$")
    description: str | None = None
    enabled: bool = True
    provider_kind: ProviderKind = Field(
        default=ProviderKind.AIRLINE,
        description="Who the provider is: airline or ticket booking agency",
    )
    api_type: ApiType = Field(
        default=ApiType.FLIGHT_SEARCH,
        description="Airline/agency ticket-booking operation; drives which aggregate route uses it",
    )
    base_url: str = Field(..., min_length=1, max_length=500)
    endpoint_path: str = Field(default="/", max_length=500)
    http_method: HttpMethod = HttpMethod.POST
    auth_type: AuthType = AuthType.NONE
    auth_config: dict[str, Any] = Field(default_factory=dict)
    default_headers: dict[str, str] = Field(default_factory=dict)
    default_params: dict[str, Any] = Field(default_factory=dict)
    request_mapping: dict[str, str] = Field(default_factory=dict)
    response_mapping: dict[str, str] = Field(default_factory=dict)
    health_check_path: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)
    adapter_key: str = Field(default="generic", max_length=100)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value.rstrip("/")


class ProviderCreate(ProviderBase):
    pass


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9\-]+$")
    description: str | None = None
    enabled: bool | None = None
    provider_kind: ProviderKind | None = None
    api_type: ApiType | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    endpoint_path: str | None = Field(default=None, max_length=500)
    http_method: HttpMethod | None = None
    auth_type: AuthType | None = None
    auth_config: dict[str, Any] | None = None
    default_headers: dict[str, str] | None = None
    default_params: dict[str, Any] | None = None
    request_mapping: dict[str, str] | None = None
    response_mapping: dict[str, str] | None = None
    health_check_path: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0, le=120)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    adapter_key: str | None = Field(default=None, max_length=100)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value.rstrip("/")


class ProviderResponse(ProviderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ProviderToggleResponse(BaseModel):
    id: int
    name: str
    enabled: bool


class ConnectivityTestRequest(BaseModel):
    sample_payload: dict[str, Any] | None = None


class ConnectivityTestResponse(BaseModel):
    success: bool
    provider_id: int
    provider_name: str
    status_code: int | None = None
    latency_ms: float | None = None
    message: str
    sample_normalized: dict[str, Any] | None = None
    raw_preview: Any = None


class CatalogItem(BaseModel):
    value: str
    label: str
    description: str
    aggregate_endpoint: str | None = None
    group: str | None = None


class TypeCatalogResponse(BaseModel):
    provider_kinds: list[CatalogItem]
    api_types: list[CatalogItem]


class AggregationParticipant(BaseModel):
    id: int
    name: str
    slug: str
    provider_kind: ProviderKind
    enabled: bool
    adapter_key: str


class AggregationMapEntry(BaseModel):
    api_type: ApiType
    label: str
    description: str
    aggregate_endpoint: str | None
    group: str | None = None
    enabled_count: int
    total_count: int
    providers: list[AggregationParticipant]


class AggregationMapResponse(BaseModel):
    """Shows which providers will be called for each API type when aggregating."""

    entries: list[AggregationMapEntry]


def build_type_catalog() -> TypeCatalogResponse:
    return TypeCatalogResponse(
        provider_kinds=[
            CatalogItem(
                value=kind.value,
                label=meta["label"],
                description=meta["description"],
            )
            for kind, meta in PROVIDER_KIND_CATALOG.items()
        ],
        api_types=[
            CatalogItem(
                value=api.value,
                label=meta["label"],
                description=meta["description"],
                aggregate_endpoint=meta.get("aggregate_endpoint"),
                group=meta.get("group"),
            )
            for api, meta in API_TYPE_CATALOG.items()
        ],
    )
