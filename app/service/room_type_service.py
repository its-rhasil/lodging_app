from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.room import RoomType

def add_room_type(db: Session, tenant_id: int, name: str, description: str| None, default_price, capacity: int):
    if default_price <= 0:
        raise HTTPException(status_code=422, detail="Default price must be greater than 0")
    if capacity <= 0:
        raise HTTPException(status_code=422, detail="Capacity must be greater than 0")

    room_type = RoomType(
            db=db,
            tenant_id = tenant_id,
            name = name,
            description = description,
            default_price = default_price,
            capacity = capacity
        )
    db.add(room_type)
    db.commit()
    db.refresh(room_type)
    return room_type

def get_room_type(db: Session, tenant_id, room_type_id: int):
    return db.query(RoomType).filter(RoomType.id == room_type_id, RoomType.tenant_id == tenant_id).first()


def list_room_type(db: Session, tenant_id):
    return db.query(RoomType).filter(RoomType.tenant_id == tenant_id).all()