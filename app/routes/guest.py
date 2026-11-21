"""Guests: lookup by phone (check-in reuse, P6-1) and search by name/phone. Needs guest.view."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.errors import ValidationFailed
from app.core.principal import Principal
from app.database import get_db
from app.schemas.guest import GuestOut
from app.service import guest_service

router = APIRouter(prefix="/guests", tags=["guests"])
can_view = require_permission("guest.view")


@router.get("", response_model=list[GuestOut])
def find_guests(phone: str | None = Query(None, min_length=1, max_length=25),
                q: str | None = Query(None, max_length=100),
                principal: Principal = Depends(can_view), db: Session = Depends(get_db)):
    """?phone= exact match after normalisation (check-in reuse); ?q= name or partial phone."""
    if (phone is None) == (q is None):
        raise ValidationFailed("Send either phone or q.", code="invalid_query")
    if phone is not None:
        return guest_service.find_by_phone(db, principal, phone)
    return guest_service.search(db, principal, q)
