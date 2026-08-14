from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import hash_password, verify_password
from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_username(self, username: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.db.get(User, user_id)

    async def create_admin(self, username: str, email: str, password: str) -> User:
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            is_active=True,
            is_admin=True,
            role="admin",
            description="Bootstrap administrator",
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def authenticate(self, username: str, password: str) -> User:
        user = await self.get_by_username(username)
        if not user or not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Invalid username or password")
        if not user.is_active:
            raise UnauthorizedError("User account is disabled")
        return user

    async def count(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(User))
        return int(result.scalar_one() or 0)

    def _filter(self, stmt, *, q: str | None, role: str | None):
        needle = (q or "").strip()
        if needle:
            like = f"%{needle}%"
            stmt = stmt.where(
                or_(
                    User.username.ilike(like),
                    User.email.ilike(like),
                    User.description.ilike(like),
                )
            )
        if role:
            stmt = stmt.where(User.role == role)
        return stmt

    async def count_users(self, *, q: str | None = None, role: str | None = None) -> int:
        stmt = self._filter(select(func.count()).select_from(User), q=q, role=role)
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def list_users(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
        q: str | None = None,
        role: str | None = None,
    ) -> list[User]:
        stmt = self._filter(select(User), q=q, role=role).order_by(User.created_at.desc())
        if limit is not None:
            stmt = stmt.offset(max(offset, 0)).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        is_admin: bool = False,
        is_active: bool = True,
        role: str = "b2b",
        description: str | None = None,
    ) -> User:
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            is_active=is_active,
            is_admin=is_admin or role == "admin",
            role=role,
            description=description,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update_user(self, user: User, **fields) -> User:
        for key, value in fields.items():
            if value is not None or key in {"email"}:
                setattr(user, key, value)
        await self.db.flush()
        await self.db.refresh(user)
        return user
