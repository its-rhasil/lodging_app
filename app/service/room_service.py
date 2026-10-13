from fastapi import HTTPException
from sqlalchemy.orm import joinedload, Session
from app.models.room import Room
from app.crud.room import get_room_with_active_stay, get_room
from app.service.status_service import set_operational_status
from app.service.room_type_service import get_room_type
from app.service.payment_service import get_billing_summary
from app.service.status_service import get_effective_status

def create_room(db: Session, tenant_id: int, room_type_id: int, room_number: int):
    room_type = get_room_type(db=db, tenant_id=tenant_id, room_type_id=room_type_id)
    if room_type is None:
        raise HTTPException(status_code=404, detail="Room Type not found!")
    room = Room(
        tenant_id = tenant_id,
        room_type_id = room_type_id,
        room_number = room_number
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return room

def get_room_detail(db: Session, tenant_id: int, room_id: int) -> dict:
    room = get_room_with_active_stay(db, tenant_id, room_id)  
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    status = get_effective_status(room)
    active_stay = room.stays[0] if room.stays else None

    return {
        "room_id": room.id,
        "stay_id": active_stay.id if active_stay else None,
        "room_number": room.room_number,
        "room_type_name": room.room_type.name,
        "status": status,
        "guest": active_stay.guest if active_stay else None,
        "actual_check_in_at": active_stay.actual_check_in_at if active_stay else None,
        "expected_checkout_at": active_stay.expected_checkout_at if active_stay else None,
        "billing": get_billing_summary(db, tenant_id, active_stay) if active_stay else None,
    }


def update_room_status(db: Session, tenant_id: int, room_id: int, new_status: str) -> Room:
    if new_status not in ("available", "cleaning", "maintenance"):
        raise HTTPException(status_code=422, detail="Invalid status")

    room = get_room_with_active_stay(db, tenant_id, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.stays:  # this is filtered to status='active' by the query's joinedload
        raise HTTPException(status_code=409, detail="Cannot change status of an occupied room")

    set_operational_status(room, new_status)
    db.commit()
    db.refresh(room)
    return room