from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import App, Target, TargetStatus, User
from app.schemas import AppCreate, AppOut, AppUpdate, TargetCreate, TargetOut, TrustPrivateRequest
from app.services.audit import write_audit
from app.services.verify import is_ip_in_trusted_nets, verify_target

router = APIRouter(tags=["apps"])


async def _bust_overview_cache(settings: Settings) -> None:
    from app.routers.findings import _invalidate_overview_cache

    await _invalidate_overview_cache(settings)


@router.get("/apps", response_model=list[AppOut])
async def list_apps(
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[App]:
    count_stmt = select(func.count()).select_from(App)
    total = await db.scalar(count_stmt) or 0

    stmt = (
        select(App)
        .options(selectinload(App.targets))
        .order_by(App.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(await db.scalars(stmt))

    has_more = (offset + len(items)) < total
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "true" if has_more else "false"

    return items


@router.post("/apps", response_model=AppOut, status_code=status.HTTP_201_CREATED)
async def create_app(
    body: AppCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> App:
    app = App(**body.model_dump())
    db.add(app)
    await db.flush()

    # auto-create primary target from base_url host
    from urllib.parse import urlparse

    host = urlparse(body.base_url).hostname or body.base_url
    target = Target(app_id=app.id, host=host, verify_token=secrets.token_urlsafe(24))
    db.add(target)
    await write_audit(
        db,
        action="app.create",
        user_id=user.id,
        entity_type="app",
        entity_id=str(app.id),
        detail=app.name,
    )
    await db.commit()
    await _bust_overview_cache(settings)

    return await db.scalar(select(App).where(App.id == app.id).options(selectinload(App.targets)))  # type: ignore[return-value]


@router.get("/apps/{app_id}", response_model=AppOut)
async def get_app(
    app_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> App:
    app = await db.scalar(select(App).where(App.id == app_id).options(selectinload(App.targets)))
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


@router.patch("/apps/{app_id}", response_model=AppOut)
async def update_app(
    app_id: uuid.UUID,
    body: AppUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> App:
    app = await db.get(App, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(app, k, v)
    await write_audit(
        db,
        action="app.update",
        user_id=user.id,
        entity_type="app",
        entity_id=str(app.id),
        detail=",".join(data.keys()),
    )
    await db.commit()
    await _bust_overview_cache(settings)

    return await db.scalar(select(App).where(App.id == app.id).options(selectinload(App.targets)))  # type: ignore[return-value]


@router.delete("/apps/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_app(
    app_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> None:
    app = await db.get(App, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    await write_audit(
        db,
        action="app.delete",
        user_id=user.id,
        entity_type="app",
        entity_id=str(app.id),
        detail=app.name,
    )
    await db.delete(app)
    await db.commit()
    await _bust_overview_cache(settings)


@router.post("/apps/{app_id}/targets", response_model=TargetOut, status_code=status.HTTP_201_CREATED)
async def add_target(
    app_id: uuid.UUID,
    body: TargetCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Target:
    app = await db.get(App, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    target = Target(app_id=app_id, host=body.host.strip(), verify_token=secrets.token_urlsafe(24))
    db.add(target)
    await write_audit(
        db,
        action="target.create",
        user_id=user.id,
        entity_type="target",
        entity_id=str(target.id),
        detail=target.host,
    )
    await db.commit()
    await db.refresh(target)
    return target


@router.post("/targets/{target_id}/verify", response_model=TargetOut)
async def verify_target_endpoint(
    target_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Target:
    target = await db.get(Target, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    app = await db.get(App, target.app_id)
    verified, method = await verify_target(target.host, target.verify_token, app.base_url if app else None)
    if not verified:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Verification failed. Add DNS TXT straz-verify={target.verify_token} "
                f"or /.well-known/straz.txt with that token."
            ),
        )
    target.status = TargetStatus.verified
    target.verify_method = method
    target.verified_at = datetime.now(timezone.utc)
    await write_audit(
        db,
        action="target.verify",
        user_id=user.id,
        entity_type="target",
        entity_id=str(target.id),
        detail=method,
    )
    await db.commit()
    await db.refresh(target)
    return target


@router.post("/targets/{target_id}/trust-private", response_model=TargetOut)
async def trust_private_target(
    target_id: uuid.UUID,
    body: TrustPrivateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Target:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true")
    target = await db.get(Target, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    if not is_ip_in_trusted_nets(target.host, settings.trusted_nets_list):
        raise HTTPException(status_code=400, detail="Host is not in TRUSTED_PRIVATE_NETS")
    target.status = TargetStatus.verified
    target.verify_method = "trusted_private"
    target.trusted_private = True
    target.verified_at = datetime.now(timezone.utc)
    await write_audit(
        db,
        action="target.trust_private",
        user_id=user.id,
        entity_type="target",
        entity_id=str(target.id),
        detail=target.host,
    )
    await db.commit()
    await db.refresh(target)
    return target
