"""Room types and rates. Reading needs room.view; changes need inventory.manage.

No try/except here: services raise DomainError subclasses (or the DB raises
IntegrityError), and the handlers in app/core/errors.py turn them into responses.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.principal import Principal
from app.core.request_context import RequestMeta, get_request_meta
from app.database import get_db
from app.schemas.room_type import RoomTypeCreate, RoomTypeOut, RoomTypeUpdate
from app.service import room_type_service

router = APIRouter(prefix="/room-types", tags=["room-types"])
can_view = require_permission("room.view")
can_manage = require_permission("inventory.manage")


@router.get("", response_model=list[RoomTypeOut])
def list_room_types(principal: Principal = Depends(can_view), db: Session = Depends(get_db)):
    return room_type_service.list_room_types(db, principal)


@router.post("", response_model=RoomTypeOut, status_code=201)
def create_room_type(payload: RoomTypeCreate, principal: Principal = Depends(can_manage),
                     db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return room_type_service.create_room_type(db, principal, meta=meta, **payload.model_dump())


@router.patch("/{room_type_id}", response_model=RoomTypeOut)
def update_room_type(room_type_id: int, payload: RoomTypeUpdate, principal: Principal = Depends(can_manage),
                     db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return room_type_service.update_room_type(
        db, principal, room_type_id, payload.model_dump(exclude_unset=True), meta=meta,
    )
