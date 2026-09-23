from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.rate_limit import client_ip, login_limiter
from app.schemas import LoginRequest, UserOut
from app.security import create_session_token, verify_password
from app.services.audit import write_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    login_limiter.check(f"login:{client_ip(request)}")
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_session_token(settings, str(user.id))
    response.set_cookie(
        key=settings.straz_cookie_name,
        value=token,
        httponly=True,
        secure=settings.straz_cookie_secure,
        samesite="lax",
        max_age=settings.straz_session_max_age,
        path="/",
    )
    await write_audit(db, action="auth.login", user_id=user.id)
    await db.commit()
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> None:
    response.delete_cookie(settings.straz_cookie_name, path="/")
    await write_audit(db, action="auth.logout", user_id=user.id)
    await db.commit()


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
