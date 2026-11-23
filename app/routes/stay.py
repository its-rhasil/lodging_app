"""Stays: check-in, checkout, extend, room change, conversion to full day.

No try/except here: services raise DomainError subclasses (or the DB raises
IntegrityError), and the handlers in app/core/errors.py turn them into responses.
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.deps import require_permission
from app.core.principal import Principal
from app.core.request_context import RequestMeta, get_request_meta
from app.database import get_db
from app.schemas.stay import (
    CancelIn, ChangeRoomIn, CheckInRequest, CheckoutIn, ConvertIn, CorrectPriceIn, ExtendIn, StayDetailOut,
    StayOut, StaySummary,
)
from app.service import folio_service, stay_read_service, stay_service

router = APIRouter(prefix="/stays", tags=["stays"])
can_view = require_permission("stay.view")
can_view_folios = require_permission("folio.view")
can_check_in = require_permission("stay.check_in")
can_check_out = require_permission("stay.check_out")
can_extend = require_permission("stay.extend")
can_change_room = require_permission("stay.change_room")
can_convert = require_permission("stay.convert_to_daily")


# Read endpoints. The fixed paths come before /{stay_id} so they aren't read as an id.

@router.get("", response_model=list[StaySummary])
def list_stays(status: Literal["active", "checked_out"] = "active",
               limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
               principal: Principal = Depends(can_view), db: Session = Depends(get_db),
               now: datetime = Depends(get_now)):
    return stay_read_service.list_stays(db, principal, status=status, limit=limit, offset=offset, now=now)


@router.get("/pending-balances", response_model=list[StaySummary])
def pending_balances(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                     principal: Principal = Depends(can_view_folios), db: Session = Depends(get_db),
                     now: datetime = Depends(get_now)):
    return stay_read_service.pending_balances(db, principal, limit=limit, offset=offset, now=now)


@router.get("/{stay_id}", response_model=StayDetailOut)
def stay_detail(stay_id: int, principal: Principal = Depends(can_view), db: Session = Depends(get_db),
                now: datetime = Depends(get_now)):
    return stay_read_service.stay_detail(db, principal, stay_id, now=now)


@router.post("", response_model=StayOut, status_code=201)
def check_in(payload: CheckInRequest, principal: Principal = Depends(can_check_in),
             db: Session = Depends(get_db), now: datetime = Depends(get_now),
             meta: RequestMeta = Depends(get_request_meta)):
    return stay_service.check_in(db, principal, now=now, meta=meta, **payload.model_dump())


@router.post("/{stay_id}/checkout", response_model=StayOut)
def checkout(stay_id: int, payload: CheckoutIn | None = None, principal: Principal = Depends(can_check_out),
             db: Session = Depends(get_db), now: datetime = Depends(get_now),
             meta: RequestMeta = Depends(get_request_meta)):
    payload = payload or CheckoutIn()
    return stay_service.checkout(db, principal, stay_id, now=now, meta=meta, **payload.model_dump())


@router.patch("/{stay_id}/extend", response_model=StayOut)
def extend(stay_id: int, payload: ExtendIn, principal: Principal = Depends(can_extend),
           db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return stay_service.extend(db, principal, stay_id, expected_checkout_at=payload.expected_checkout_at,
                               meta=meta)


@router.post("/{stay_id}/change-room", response_model=StayOut)
def change_room(stay_id: int, payload: ChangeRoomIn, principal: Principal = Depends(can_change_room),
                db: Session = Depends(get_db), now: datetime = Depends(get_now),
                meta: RequestMeta = Depends(get_request_meta)):
    return stay_service.change_room(db, principal, stay_id, now=now, meta=meta, **payload.model_dump())


@router.post("/{stay_id}/cancel", response_model=StayOut)
def cancel_check_in(stay_id: int, payload: CancelIn, principal: Principal = Depends(can_check_in),
                    db: Session = Depends(get_db), now: datetime = Depends(get_now),
                    meta: RequestMeta = Depends(get_request_meta)):
    """The desk within 30 minutes of check-in; a manager (folio.reverse) any time."""
    return folio_service.cancel_stay(db, principal, stay_id, reason=payload.reason, now=now, meta=meta)


@router.post("/{stay_id}/correct-price", response_model=StayOut)
def correct_price(stay_id: int, payload: CorrectPriceIn,
                  principal: Principal = Depends(require_permission("folio.reverse")),
                  db: Session = Depends(get_db), now: datetime = Depends(get_now),
                  meta: RequestMeta = Depends(get_request_meta)):
    """Manager-only (it reverses posted charges), like other reversals."""
    return folio_service.correct_price(db, principal, stay_id, now=now, meta=meta, **payload.model_dump())


@router.post("/{stay_id}/convert-to-daily", response_model=StayOut)
def convert_to_daily(stay_id: int, payload: ConvertIn | None = None, principal: Principal = Depends(can_convert),
                     db: Session = Depends(get_db), now: datetime = Depends(get_now),
                     meta: RequestMeta = Depends(get_request_meta)):
    payload = payload or ConvertIn()
    return folio_service.convert_to_daily(db, principal, stay_id, now=now, meta=meta, **payload.model_dump())
