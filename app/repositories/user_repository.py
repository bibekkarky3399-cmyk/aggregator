from sqlalchemy import select
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
        result = await self.db.execute(select(User))
        return len(list(result.scalars().all()))
