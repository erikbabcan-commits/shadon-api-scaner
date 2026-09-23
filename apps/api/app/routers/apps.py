from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
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


@router.get("/apps", response_model=list[AppOut])
async def list_apps(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[App]:
    result = await db.scalars(select(App).options(selectinload(App.targets)).order_by(App.created_at.desc()))
    return list(result)


@router.post("/apps", response_model=AppOut, status_code=status.HTTP_201_CREATED)
async def create_app(
    body: AppCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
    await db.refresh(app, attribute_names=["targets"])
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
) -> App:
    app = await db.scalar(select(App).where(App.id == app_id).options(selectinload(App.targets)))
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(app, key, value)
    await write_audit(db, action="app.update", user_id=user.id, entity_type="app", entity_id=str(app.id))
    await db.commit()
    return await db.scalar(  # type: ignore[return-value]
        select(App).where(App.id == app_id).options(selectinload(App.targets))
    )


@router.delete("/apps/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_app(
    app_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    app = await db.get(App, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    await write_audit(db, action="app.delete", user_id=user.id, entity_type="app", entity_id=str(app.id))
    await db.delete(app)
    await db.commit()


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
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    method = await verify_target(
        host=target.host,
        base_url=app.base_url,
        token=target.verify_token,
        settings=settings,
    )
    if not method:
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
