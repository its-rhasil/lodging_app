"""Audit trail of the caller's tenant (P3-5). Needs audit.view."""
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.principal import Principal
from app.database import get_db
from app.schemas.audit import AuditEventOut
from app.service import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(date_from: AwareDatetime | None = None, date_to: AwareDatetime | None = None,
                      actor_user_id: int | None = None, action: str | None = Query(None, max_length=64),
                      entity_type: str | None = Query(None, max_length=64),
                      entity_id: str | None = Query(None, max_length=64),
                      limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                      principal: Principal = Depends(require_permission("audit.view")),
                      db: Session = Depends(get_db)):
    return audit_service.list_events(
        db, principal.tenant_id, date_from=date_from, date_to=date_to, actor_user_id=actor_user_id,
        action=action, entity_type=entity_type, entity_id=entity_id, limit=limit, offset=offset,
    )
