"""Folio of a stay: view, charge, payment, refund, waive, reverse (P4-5).

Every endpoint posts due room charges first (owner decision 2026-11-16).
No try/except here: services raise DomainError subclasses (or the DB raises
IntegrityError), and the handlers in app/core/errors.py turn them into responses.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.deps import require_permission
from app.core.principal import Principal
from app.core.request_context import RequestMeta, get_request_meta
from app.database import get_db
from app.schemas.folio import ChargeIn, FolioOut, PaymentIn, RefundIn, ReverseIn, WaiveIn
from app.service import folio_service

router = APIRouter(prefix="/stays/{stay_id}/folio", tags=["folio"])


@router.get("", response_model=FolioOut)
def view_folio(stay_id: int, principal: Principal = Depends(require_permission("folio.view")),
               db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    return folio_service.view_folio(db, principal, stay_id, now=now)


@router.post("/charges", response_model=FolioOut, status_code=201)
def post_charge(stay_id: int, payload: ChargeIn,
                principal: Principal = Depends(require_permission("folio.post_charge")),
                db: Session = Depends(get_db), now: datetime = Depends(get_now),
                meta: RequestMeta = Depends(get_request_meta)):
    return folio_service.post_charge(db, principal, stay_id, now=now, meta=meta, **payload.model_dump())


@router.post("/payments", response_model=FolioOut, status_code=201)
def record_payment(stay_id: int, payload: PaymentIn, response: Response,
                   principal: Principal = Depends(require_permission("payment.record")),
                   db: Session = Depends(get_db), now: datetime = Depends(get_now),
                   meta: RequestMeta = Depends(get_request_meta)):
    folio, created = folio_service.record_payment(db, principal, stay_id, now=now, meta=meta,
                                                  **payload.model_dump())
    if not created:
        response.status_code = 200  # a repeat of a payment already recorded
    return folio


@router.post("/refunds", response_model=FolioOut, status_code=201)
def record_refund(stay_id: int, payload: RefundIn,
                  principal: Principal = Depends(require_permission("payment.refund")),
                  db: Session = Depends(get_db), now: datetime = Depends(get_now),
                  meta: RequestMeta = Depends(get_request_meta)):
    return folio_service.record_refund(db, principal, stay_id, now=now, meta=meta, **payload.model_dump())


@router.post("/transactions/{txn_id}/waive", response_model=FolioOut, status_code=201)
def waive(stay_id: int, txn_id: int, payload: WaiveIn,
          principal: Principal = Depends(require_permission("folio.waive")),
          db: Session = Depends(get_db), now: datetime = Depends(get_now),
          meta: RequestMeta = Depends(get_request_meta)):
    return folio_service.waive(db, principal, stay_id, txn_id, now=now, meta=meta, **payload.model_dump())


@router.post("/transactions/{txn_id}/reverse", response_model=FolioOut, status_code=201)
def reverse(stay_id: int, txn_id: int, payload: ReverseIn,
            principal: Principal = Depends(require_permission("folio.reverse")),
            db: Session = Depends(get_db), now: datetime = Depends(get_now),
            meta: RequestMeta = Depends(get_request_meta)):
    return folio_service.reverse(db, principal, stay_id, txn_id, now=now, meta=meta, **payload.model_dump())
