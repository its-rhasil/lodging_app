# app/crud/room_type.py
from sqlalchemy.orm import Session, joinedload

from app.models.room import RoomType, RoomTypePrice
from decimal import Decimal

def create_room_type(
    db: Session,
    tenant_id: int,
    name: str,
    description: str | None,
    capacity: int,
    prices: list[tuple[int, Decimal]],
) -> RoomType:
    room_type = RoomType(
        tenant_id=tenant_id,
        name=name,
        description=description,
        capacity=capacity,
    )
    db.add(room_type)
    db.flush()  

    for occupancy, price in prices:
        db.add(RoomTypePrice(room_type_id=room_type.id, occupancy=occupancy, price=price))

    db.commit()
    db.refresh(room_type)
    return room_type


def get_room_type(db: Session, tenant_id: int, room_type_id: int) -> RoomType | None:
    return (
        db.query(RoomType)
        .filter(RoomType.id == room_type_id, RoomType.tenant_id == tenant_id)
        .options(joinedload(RoomType.prices))
        .first()
    )


def list_room_types(db: Session, tenant_id: int) -> list[RoomType]:
    return (
        db.query(RoomType)
        .filter(RoomType.tenant_id == tenant_id)
        .options(joinedload(RoomType.prices))
        .all()
    )

def list_room_types_without_price(db: Session, tenant_id: int) -> list[RoomType]:
    return (
        db.query(RoomType)
        .filter(RoomType.tenant_id == tenant_id)
        .all()
    )

def get_price_for_occupancy(db: Session, room_type_id: int, occupancy: int) -> RoomTypePrice | None:
    return (
        db.query(RoomTypePrice)
        .filter(RoomTypePrice.room_type_id == room_type_id, RoomTypePrice.occupancy == occupancy)
        .first()
    )