"""Tenant user administration. Every route needs user.manage."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.principal import Principal
from app.core.request_context import RequestMeta, get_request_meta
from app.database import get_db
from app.schemas.users import OverridesUpdate, UserCreate, UserDetail, UserOut
from app.service import user_service

router = APIRouter(prefix="/users", tags=["users"])
can_manage_users = require_permission("user.manage")


@router.get("", response_model=list[UserOut])
def list_users(principal: Principal = Depends(can_manage_users), db: Session = Depends(get_db)):
    return user_service.list_users(db, principal)


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, principal: Principal = Depends(can_manage_users),
                db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return user_service.create_user(db, principal, meta=meta, **payload.model_dump())


@router.get("/{user_id}", response_model=UserDetail)
def get_user(user_id: int, principal: Principal = Depends(can_manage_users), db: Session = Depends(get_db)):
    return user_service.get_user_detail(db, principal, user_id)


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(user_id: int, principal: Principal = Depends(can_manage_users),
                    db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return user_service.deactivate_user(db, principal, user_id, meta=meta)


@router.put("/{user_id}/overrides", response_model=UserDetail)
def set_overrides(user_id: int, payload: OverridesUpdate, principal: Principal = Depends(can_manage_users),
                  db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    overrides = [o.model_dump() for o in payload.overrides]
    return user_service.set_overrides(db, principal, user_id, overrides, meta=meta)
