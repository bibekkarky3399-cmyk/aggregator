from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.provider import ApiType, Provider, ProviderKind
from app.schemas.provider import ProviderCreate, ProviderUpdate


class ProviderRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(
        self,
        *,
        enabled_only: bool = False,
        api_type: ApiType | None = None,
        provider_kind: ProviderKind | None = None,
    ) -> list[Provider]:
        stmt = select(Provider).order_by(Provider.api_type, Provider.name)
        if enabled_only:
            stmt = stmt.where(Provider.enabled.is_(True))
        if api_type is not None:
            stmt = stmt.where(Provider.api_type == api_type)
        if provider_kind is not None:
            stmt = stmt.where(Provider.provider_kind == provider_kind)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, provider_id: int) -> Provider | None:
        return await self.db.get(Provider, provider_id)

    async def get_by_slug(self, slug: str) -> Provider | None:
        result = await self.db.execute(select(Provider).where(Provider.slug == slug))
        return result.scalar_one_or_none()

    async def get_by_slugs(
        self,
        slugs: list[str],
        *,
        enabled_only: bool = True,
        api_type: ApiType | None = None,
    ) -> list[Provider]:
        stmt = select(Provider).where(Provider.slug.in_(slugs))
        if enabled_only:
            stmt = stmt.where(Provider.enabled.is_(True))
        if api_type is not None:
            stmt = stmt.where(Provider.api_type == api_type)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: ProviderCreate) -> Provider:
        existing = await self.get_by_slug(data.slug)
        if existing:
            raise ConflictError(f"Provider with slug '{data.slug}' already exists")

        by_name = await self.db.execute(select(Provider).where(Provider.name == data.name))
        if by_name.scalar_one_or_none():
            raise ConflictError(f"Provider with name '{data.name}' already exists")

        provider = Provider(**data.model_dump())
        self.db.add(provider)
        await self.db.flush()
        await self.db.refresh(provider)
        return provider

    async def update(self, provider_id: int, data: ProviderUpdate) -> Provider:
        provider = await self.get_by_id(provider_id)
        if not provider:
            raise NotFoundError(f"Provider {provider_id} not found")

        updates = data.model_dump(exclude_unset=True)
        if "slug" in updates and updates["slug"] != provider.slug:
            conflict = await self.get_by_slug(updates["slug"])
            if conflict:
                raise ConflictError(f"Provider with slug '{updates['slug']}' already exists")

        for key, value in updates.items():
            setattr(provider, key, value)

        await self.db.flush()
        await self.db.refresh(provider)
        return provider

    async def delete(self, provider_id: int) -> None:
        provider = await self.get_by_id(provider_id)
        if not provider:
            raise NotFoundError(f"Provider {provider_id} not found")
        await self.db.delete(provider)
        await self.db.flush()

    async def set_enabled(self, provider_id: int, enabled: bool) -> Provider:
        provider = await self.get_by_id(provider_id)
        if not provider:
            raise NotFoundError(f"Provider {provider_id} not found")
        provider.enabled = enabled
        await self.db.flush()
        await self.db.refresh(provider)
        return provider
