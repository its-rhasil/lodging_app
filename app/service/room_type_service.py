from fastapi import HTTPException
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.room import RoomType, RoomTypePrice
from app.crud import room_type

def add_room_type(db: Session, tenant_id: int, name: str, description: str| None, capacity: int, prices: list[tuple[int, Decimal]]):

    if capacity <= 0:
        raise ValueError("capacity must be greater than zero")

    if not prices:
        raise ValueError("At least one price is required")

    seen_occupancies = set()
    for occupancy, price in prices:
        if occupancy <= 0:
            raise ValueError("Occupancy must be greater than zero.")
        if occupancy > capacity:
            raise ValueError(f"occupancy {occupancy} exceeds room type capacity {capacity}")
        if price <= 0:
            raise ValueError("price must be greater than zero")
        if occupancy in seen_occupancies:
            raise ValueError(f"duplicate price entry for occupancy {occupancy}")
        seen_occupancies.add(occupancy)

    return room_type.create_room_type(db, tenant_id, name, description, capacity, prices)


def get_room_type(db: Session, tenant_id, room_type_id: int):
    return db.query(RoomType).filter(RoomType.id == room_type_id, RoomType.tenant_id == tenant_id).first() 


def update_room_type(
    db: Session,
    room_type_id: int,
    tenant_id: int,
    name: str | None = None,
    description: str | None = None,
    capacity: int | None = None,
    prices=None,
):
    room_type = (
        db.query(RoomType)
        .filter(
            RoomType.id == room_type_id,
            RoomType.tenant_id == tenant_id
        )
        .first()
    )

    if not room_type:
        raise ValueError("Room type not found")


    new_capacity = (
        capacity
        if capacity is not None
        else room_type.capacity
    )

    if new_capacity <= 0:
        raise ValueError("Capacity must be greater than 0")

    if prices is not None:

        seen_occupancies = set()

        for price_data in prices:

            occupancy = price_data.occupancy
            price = price_data.price

            if occupancy <= 0:
                raise ValueError(
                    "Occupancy must be greater than 0"
                )

            if occupancy > new_capacity:
                raise ValueError(
                    f"Occupancy {occupancy} cannot exceed "
                    f"capacity {new_capacity}"
                )

            if price <= 0:
                raise ValueError(
                    "Price must be greater than 0"
                )

            if occupancy in seen_occupancies:
                raise ValueError(
                    f"Duplicate occupancy: {occupancy}"
                )

            seen_occupancies.add(occupancy)

        required_occupancies = set(
            range(1, new_capacity + 1)
        )

        if seen_occupancies != required_occupancies:
            raise ValueError(
                "A price must be provided for every occupancy "
                f"from 1 to {new_capacity}"
            )

    if name is not None:
        room_type.name = name

    if description is not None:
        room_type.description = description

    if capacity is not None:
        room_type.capacity = capacity

    if prices is not None:

        db.query(RoomTypePrice).filter(
            RoomTypePrice.room_type_id == room_type.id
        ).delete(
            synchronize_session=False
        )

        for price_data in prices:
            db.add(
                RoomTypePrice(
                    room_type_id=room_type.id,
                    occupancy=price_data.occupancy,
                    price=price_data.price
                )
            )

    db.commit()
    db.refresh(room_type)

    return room_type