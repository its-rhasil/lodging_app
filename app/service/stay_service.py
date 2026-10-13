from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.models.stay import Stay
from app.models.room import Room
from app.crud.room import get_room
from app.service.payment_service import get_billing_summary, calculate_nights
from app.service.status_service import set_operational_status, get_effective_status
from app.service import guest_service
from app.crud.room_type import get_price_for_occupancy
from app.crud.stay import get_stay

def preview_check_in(db: Session, tenant_id: int, room_id: int, occupancy: int) -> dict:
    room = get_room(db, tenant_id, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if occupancy <= 0:
        raise HTTPException(
                status_code=422,
                detail="Occupancy must be at least 1"
            )

    if occupancy > room.room_type.capacity:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum occupancy for this room is {room.room_type.capacity}"
        )

    current_status = get_effective_status(room)
    if current_status != "available":
        raise HTTPException(status_code=409, detail=f"Room is not available(currently {current_status})")

    price_row = get_price_for_occupancy(db, room.room_type_id, occupancy)
    suggested_price = price_row.price if price_row else None

    return {
        "room_id": room.id,
        "room_type_name": room.room_type.name,
        "occupancy": occupancy,
        "capacity": room.room_type.capacity,
        "suggested_price": suggested_price,
    }

def check_in(
    db: Session, tenant_id: int, room_id: int,
    guest_full_name: str, guest_phone: str, guest_email: str | None, guest_address: str | None,
    occupancy: int, stay_hours: int, agreed_price: Decimal,
    actual_check_in_at: datetime | None = None,
):
    room = get_room(db=db, tenant_id=tenant_id, room_id=room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    if get_effective_status(room) != "available":
        raise HTTPException(status_code=409, detail="Room is not available")

    if stay_hours <= 0:
        raise HTTPException(status_code=422, detail="Stay hours should be greater than 0")
    if agreed_price is None or agreed_price <= 0:
        raise HTTPException(status_code=422, detail="agreed_price is required and must be greater than zero")

    check_in_time = actual_check_in_at or datetime.now(timezone.utc)

    if check_in_time > datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="check-in time cannot be in the future")

    expected_checkout_at = check_in_time + timedelta(hours=stay_hours)

    guest = guest_service.create_guest(
        db=db, tenant_id=tenant_id, full_name=guest_full_name,
        phone=guest_phone, email=guest_email, address=guest_address,
    )

    stay = Stay(
        tenant_id=tenant_id,
        room_id=room_id,
        guest_id=guest.id,
        status="active",
        actual_check_in_at=check_in_time,
        expected_checkout_at=expected_checkout_at,
        agreed_price=agreed_price,
        occupancy=occupancy,
    )
    db.add(stay)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Room already has an active stay")

    db.refresh(stay)
    return stay

def checkout_stay(stay: Stay, actual_checkout_at):
    stay.status = "checked_out"
    stay.actual_checkout_at = actual_checkout_at
    return stay



def check_out(db: Session, tenant_id: int, stay_id: int, force: bool = False) -> dict:
    stay = get_stay(db, tenant_id, stay_id)
    if stay is None:
        raise HTTPException(status_code=404, detail="Stay not found")
    if stay.status != "active":
        raise HTTPException(status_code=409, detail="Stay is not active")

    room = get_room(db, tenant_id, stay.room_id)

    billing = get_billing_summary(db, tenant_id, stay)
    if billing["balance"] > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={"message": "Outstanding balance", "balance": str(billing["balance"])},
        )


    checkout_stay(stay, actual_checkout_at=datetime.now(timezone.utc))
    set_operational_status(room, "cleaning")

    db.commit()
    db.refresh(stay)

    billing = get_billing_summary(db, tenant_id, stay)
    return {"stay": stay, "billing": billing}

def extend_stay(db: Session, tenant_id: int, stay_id: int, new_expected_checkout_at):
    stay = get_stay(db, tenant_id, stay_id)
    if stay is None:
        raise HTTPException(status_code=404, detail="Stay not found")
    if stay.status != "active":
        raise HTTPException(status_code=409, detail="Stay is not active")
    if new_expected_checkout_at <= stay.actual_check_in_at:
        raise HTTPException(status_code=422, detail="new checkout must be after check-in")
    if stay.expected_checkout_at is not None and new_expected_checkout_at <= stay.expected_checkout_at:
        raise HTTPException(status_code=422, detail="new checkout must be later than the current one")

    stay.expected_checkout_at = new_expected_checkout_at
    db.commit()
    db.refresh(stay)
    return stay

def preview_room_change(db: Session, tenant_id: int, stay_id: int, new_room_id: int) -> dict:
    stay = get_stay(db, tenant_id, stay_id)
    if stay is None:
        raise HTTPException(status_code=404, detail="Stay not found")
    if stay.status != "active":
        raise HTTPException(status_code=409, detail="Stay is not active")

    new_room = get_room(db, tenant_id, new_room_id)
    if new_room is None:
        raise HTTPException(status_code=404, detail="New room not found")
    if new_room.id == stay.room_id:
        raise HTTPException(status_code=422, detail="Already in this room")
    if get_effective_status(new_room) != "available":
        raise HTTPException(status_code=409, detail="New room is not available")

    now = datetime.now(timezone.utc)
    nights_so_far = calculate_nights(stay.actual_check_in_at, now)
    mode = "updated" if nights_so_far <= 1 else "split"

    price_row = get_price_for_occupancy(db, new_room.room_type_id, stay.occupancy)
    suggested_price = price_row.price if price_row else None

    old_balance = None
    if mode == "split":
        old_balance = get_billing_summary(db, tenant_id, stay)["balance"]

    return {
        "mode": mode,
        "suggested_price": suggested_price,
        "old_balance_due_if_split": old_balance,
    }


def confirm_room_change(
    db: Session, tenant_id: int, stay_id: int, new_room_id: int, final_price: Decimal, force: bool = False
) -> dict:
    stay = get_stay(db, tenant_id, stay_id)
    if stay is None:
        raise HTTPException(status_code=404, detail="Stay not found")
    if stay.status != "active":
        raise HTTPException(status_code=409, detail="Stay is not active")

    new_room = get_room(db, tenant_id, new_room_id)
    if new_room is None:
        raise HTTPException(status_code=404, detail="New room not found")
    if new_room.id == stay.room_id:
        raise HTTPException(status_code=422, detail="Already in this room")

    if final_price is None or final_price <= 0:
        raise HTTPException(status_code=422, detail="final_price is required and must be greater than zero")

    now = datetime.now(timezone.utc)
    nights_so_far = calculate_nights(stay.actual_check_in_at, now)

    if nights_so_far <= 1:
        stay.room_id = new_room_id
        stay.agreed_price = final_price
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="New room already has an active stay")
        db.refresh(stay)
        return {"mode": "updated", "stay": stay}

    old_billing = get_billing_summary(db, tenant_id, stay)
    if old_billing["balance"] > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={"message": "Outstanding balance on current room", "balance": str(old_billing["balance"])},
        )

    checkout_stay(stay, actual_checkout_at=now)
    old_room = get_room(db, tenant_id, stay.room_id)
    set_operational_status(old_room, "cleaning")

    new_stay = Stay(
        tenant_id=tenant_id,
        room_id=new_room_id,
        guest_id=stay.guest_id,
        status="active",
        actual_check_in_at=now,
        expected_checkout_at= stay.expected_checkout_at,
        agreed_price=final_price,
        occupancy=stay.occupancy,
    )
    db.add(new_stay)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="New room already has an active stay")

    db.refresh(new_stay)
    return {"mode": "split", "old_stay": stay, "new_stay": new_stay}