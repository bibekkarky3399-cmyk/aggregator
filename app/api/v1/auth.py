from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token
from app.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await UserRepository(db).authenticate(body.username, body.password)
    if not user.is_admin:
        raise UnauthorizedError("Only administrators can sign in to the dashboard")
    token = create_access_token(subject=user.username, extra_claims={"admin": True})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_admin)) -> User:
    return current_user
