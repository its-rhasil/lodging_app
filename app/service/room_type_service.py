from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.crud.room_type import create_room_type

def add_room_type(db: Session, tenant_id: int, name: str, description: str| None, default_price, capacity: int):
    if default_price <= 0:
        raise HTTPException(status_code=422, detail="Default price must be greater than 0")
    if capacity <= 0:
        raise HTTPException(status_code=422, detail="Capacity must be greater than 0")

    return create_room_type(db=db, tenant_id=tenant_id, name= name, description=description, default_price=default_price,capacity=capacity)
