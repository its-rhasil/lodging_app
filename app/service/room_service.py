from fastapi import HTTPException
from sqlalchemy.orm import joinedload, Session
from app.models.room import Room
from app.models.stay import Stay
from app.service.room_type_service import get_room_type


def create_room(db: Session, tenant_id: int, room_type_id: int, room_number: int):
    room_type = get_room_type(db=db, tenant_id=tenant_id, room_type_id=room_type_id)
    if room_type is None:
        raise HTTPException(status_code=404, detail="Room not found!")
    
    room = Room(
        tenant_id = tenant_id,
        room_type_id = room_type_id,
        room_number = room_number
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return room



def get_room_for_dashboard(db: Session, tenant_id: int) -> list[Room]:
    return db.query(Room).filter(
        Room.tenant_id == tenant_id
    ).options(
        joinedload(Room.stays.and_(Stay.status == "active")).joinedload(Stay.guest).all()
    )