"""Tenant settings. Every staff member can read them (the screens need the timezone and
currency); only settings.manage can change them."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.principal import Principal
from app.core.request_context import RequestMeta, get_request_meta
from app.database import get_db
from app.schemas.settings import SettingsOut, SettingsUpdate
from app.service import tenant_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def read_settings(principal: Principal = Depends(require_permission("dashboard.view")),
                  db: Session = Depends(get_db)):
    return tenant_service.get_settings(db, principal.tenant_id)


@router.patch("", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, principal: Principal = Depends(require_permission("settings.manage")),
                    db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return tenant_service.update_settings(db, principal, payload.model_dump(exclude_unset=True), meta=meta)
