"""Rooms. Reading needs room.view; setup needs inventory.manage; status needs room.status.update.

No try/except here: services raise DomainError subclasses (or the DB raises
IntegrityError), and the handlers in app/core/errors.py turn them into responses.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.principal import Principal
from app.core.request_context import RequestMeta, get_request_meta
from app.database import get_db
from app.schemas.room import RoomCreate, RoomOut, RoomStatusUpdate, RoomUpdate
from app.schemas.stay import OfferOut
from app.service import room_service, stay_service

router = APIRouter(prefix="/rooms", tags=["rooms"])
can_view = require_permission("room.view")
can_manage = require_permission("inventory.manage")
can_set_status = require_permission("room.status.update")
can_check_in = require_permission("stay.check_in")


@router.get("", response_model=list[RoomOut])
def list_rooms(principal: Principal = Depends(can_view), db: Session = Depends(get_db)):
    return room_service.list_rooms(db, principal)


@router.get("/{room_id}", response_model=RoomOut)
def get_room(room_id: int, principal: Principal = Depends(can_view), db: Session = Depends(get_db)):
    return room_service.room_detail(db, principal, room_id)


@router.get("/{room_id}/offers", response_model=list[OfferOut])
def list_room_offers(room_id: int, occupancy: int = Query(ge=1), principal: Principal = Depends(can_check_in),
                     db: Session = Depends(get_db)):
    """The check-in plan picker: plans this room offers at this occupancy, with listed prices."""
    return stay_service.list_offers(db, principal, room_id, occupancy)


@router.post("", response_model=RoomOut, status_code=201)
def create_room(payload: RoomCreate, principal: Principal = Depends(can_manage),
                db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return room_service.create_room(db, principal, meta=meta, **payload.model_dump())


@router.patch("/{room_id}", response_model=RoomOut)
def update_room(room_id: int, payload: RoomUpdate, principal: Principal = Depends(can_manage),
                db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return room_service.update_room(db, principal, room_id, payload.model_dump(exclude_unset=True), meta=meta)


@router.patch("/{room_id}/status", response_model=RoomOut)
def set_room_status(room_id: int, payload: RoomStatusUpdate, principal: Principal = Depends(can_set_status),
                    db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return room_service.set_status(db, principal, room_id, payload.operational_status, meta=meta)
