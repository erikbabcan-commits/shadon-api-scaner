from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.rate_limit import change_password_limiter, client_ip, login_limiter
from app.schemas import ChangePasswordRequest, LoginRequest, RegisterRequest, UserOut
from app.security import create_session_token, hash_password, verify_password
from app.services.audit import write_audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookie(response: Response, token: str, settings: Settings) -> None:
    cookie_name = (
        f"__Host-{settings.straz_cookie_name}"
        if settings.straz_cookie_secure
        else settings.straz_cookie_name
    )
    samesite = settings.straz_cookie_samesite.lower()
    # RFC6265 requires Secure if SameSite=None
    secure = settings.straz_cookie_secure or samesite == "none"

    response.set_cookie(
        key=cookie_name,
        value=token,
        httponly=True,
        secure=secure,
        samesite=samesite,  # type: ignore[arg-type]
        domain=settings.straz_cookie_domain,
        max_age=settings.straz_session_max_age,
        path="/",
    )
    if settings.straz_cookie_secure:
        response.set_cookie(
            key=settings.straz_cookie_name,
            value=token,
            httponly=True,
            secure=secure,
            samesite=samesite,  # type: ignore[arg-type]
            domain=settings.straz_cookie_domain,
            max_age=settings.straz_session_max_age,
            path="/",
        )


def _clear_auth_cookie(response: Response, settings: Settings) -> None:
    cookie_name = (
        f"__Host-{settings.straz_cookie_name}"
        if settings.straz_cookie_secure
        else settings.straz_cookie_name
    )
    response.delete_cookie(cookie_name, path="/", domain=settings.straz_cookie_domain)
    response.delete_cookie(settings.straz_cookie_name, path="/", domain=settings.straz_cookie_domain)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    await login_limiter.check(f"register:{client_ip(request)}", response=response)
    existing = await db.scalar(select(User).where(User.email == body.email.lower()))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Používateľ s týmto emailom už existuje",
        )

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_session_token(settings, str(user.id), user.token_version)
    _set_auth_cookie(response, token, settings)

    await write_audit(db, action="auth.register", user_id=user.id)
    await db.commit()
    return user


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    await login_limiter.check(f"login:{client_ip(request)}", response=response)
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_session_token(settings, str(user.id), user.token_version)
    _set_auth_cookie(response, token, settings)

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
    _clear_auth_cookie(response, settings)
    await write_audit(db, action="auth.logout", user_id=user.id)
    await db.commit()


@router.post("/change-password", response_model=UserOut)
async def change_password(
    body: ChangePasswordRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    await change_password_limiter.check(f"change_pwd:{user.id}", response=response)

    if not verify_password(user.password_hash, body.old_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pôvodné heslo nie je správne",
        )

    if body.old_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nové heslo musí byť iné ako pôvodné heslo",
        )

    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # Invalidate any older sessions across all browsers

    new_token = create_session_token(settings, str(user.id), user.token_version)
    _set_auth_cookie(response, new_token, settings)

    await write_audit(db, action="auth.change_password", user_id=user.id)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
