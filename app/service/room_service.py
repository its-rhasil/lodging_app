"""Rooms (P1-10) and room status changes (P1-5, P2-3).

Effective status (DL-E04): 'occupied' if the room has an active stay, otherwise the
stored operational_status (available / cleaning / maintenance).

Locking: changes lock the room row (FOR UPDATE) before checking for an active stay.
Check-in locks the same row, so a status change and a check-in on one room can't
interleave (architecture.md §10).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.principal import Principal
from app.core.request_context import RequestMeta
from app.models import Room, RoomType, Stay
from app.service import audit_service
from app.service.room_type_service import get_room_type

EDITABLE_FIELDS = ("room_type_id", "room_number", "is_active")


def active_stay_ids(db: Session, tenant_id: int, room_ids: list[int]) -> dict[int, int]:
    """room_id -> id of its active stay, for the rooms that have one (one query)."""
    if not room_ids:
        return {}
    rows = db.execute(
        select(Stay.room_id, Stay.id)
        .where(Stay.tenant_id == tenant_id, Stay.status == "active", Stay.room_id.in_(room_ids))
    )
    return {room_id: stay_id for room_id, stay_id in rows}


def _out(room: Room, room_type_name: str, stay_id: int | None) -> dict:
    return {
        "id": room.id, "room_number": room.room_number, "room_type_id": room.room_type_id,
        "room_type_name": room_type_name, "operational_status": room.operational_status,
        "status": "occupied" if stay_id else room.operational_status,
        "active_stay_id": stay_id, "is_active": room.is_active, "created_at": room.created_at,
    }


def get_room(db: Session, tenant_id: int, room_id: int, *, lock: bool = False) -> Room:
    """A room of this tenant. Another tenant's room is reported as not found."""
    query = select(Room).where(Room.tenant_id == tenant_id, Room.id == room_id)
    if lock:
        query = query.with_for_update()
    room = db.scalars(query).first()
    if room is None:
        raise NotFound("Room not found.", code="room_not_found")
    return room


def list_rooms(db: Session, principal: Principal) -> list[dict]:
    rows = db.execute(
        select(Room, RoomType.name)
        .join(RoomType, (RoomType.tenant_id == Room.tenant_id) & (RoomType.id == Room.room_type_id))
        .where(Room.tenant_id == principal.tenant_id)
        .order_by(Room.room_number)
    ).all()
    stays = active_stay_ids(db, principal.tenant_id, [room.id for room, _ in rows])
    return [_out(room, type_name, stays.get(room.id)) for room, type_name in rows]


def room_detail(db: Session, principal: Principal, room_id: int) -> dict:
    room = get_room(db, principal.tenant_id, room_id)
    return _detail(db, room)


def _detail(db: Session, room: Room) -> dict:
    room_type = get_room_type(db, room.tenant_id, room.room_type_id)
    stay_id = active_stay_ids(db, room.tenant_id, [room.id]).get(room.id)
    return _out(room, room_type.name, stay_id)


def _usable_room_type(db: Session, tenant_id: int, room_type_id: int) -> RoomType:
    room_type = get_room_type(db, tenant_id, room_type_id)
    if not room_type.is_active:
        raise ValidationFailed("This room type is inactive.", code="room_type_inactive")
    return room_type


def create_room(db: Session, principal: Principal, *, room_type_id: int, room_number: str,
                meta: RequestMeta) -> dict:
    room_number = room_number.strip()
    if not room_number:
        raise ValidationFailed("Room number is required.", code="field_required", details={"field": "room_number"})
    _usable_room_type(db, principal.tenant_id, room_type_id)
    room = Room(tenant_id=principal.tenant_id, room_type_id=room_type_id, room_number=room_number)
    db.add(room)
    db.flush()  # a taken number fails here: uq_room_number_per_tenant -> 409 room_number_taken
    audit_service.record(
        db, action="room.created", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="room", entity_id=room.id, summary=f"Created room {room_number}",
        changes={"room_number": [None, room_number], "room_type_id": [None, room_type_id]}, meta=meta,
    )
    db.commit()
    return _detail(db, room)


def update_room(db: Session, principal: Principal, room_id: int, fields: dict, *,
                meta: RequestMeta) -> dict:
    """`fields` holds only what the client sent (exclude_unset)."""
    room = get_room(db, principal.tenant_id, room_id, lock=True)
    if fields.get("room_number") is not None:
        fields["room_number"] = fields["room_number"].strip()
        if not fields["room_number"]:
            raise ValidationFailed("Room number is required.", code="field_required",
                                   details={"field": "room_number"})
    fields = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS and v is not None}
    changes = {k: [getattr(room, k), v] for k, v in fields.items() if getattr(room, k) != v}
    if not changes:
        return _detail(db, room)

    if "room_type_id" in changes:
        _usable_room_type(db, principal.tenant_id, changes["room_type_id"][1])
    # A guest's occupancy and price were based on the current type, and an occupied room
    # can't disappear from the grid: both wait until the room is empty.
    if "room_type_id" in changes or changes.get("is_active", [None, True])[1] is False:
        if active_stay_ids(db, principal.tenant_id, [room.id]):
            raise Conflict("The room has a guest. Check them out or move them first.", code="room_occupied")

    for key, (_, new) in changes.items():
        setattr(room, key, new)
    db.flush()  # uq_room_number_per_tenant on a renumber
    audit_service.record(
        db, action="room.updated", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="room", entity_id=room.id, summary=f"Updated room {room.room_number}",
        changes=changes, meta=meta,
    )
    db.commit()
    return _detail(db, room)


def set_status(db: Session, principal: Principal, room_id: int, new_status: str, *,
               meta: RequestMeta) -> dict:
    """Staff sets available / cleaning / maintenance. Not allowed while a guest is in the room."""
    room = get_room(db, principal.tenant_id, room_id, lock=True)
    if active_stay_ids(db, principal.tenant_id, [room.id]):
        raise Conflict("The room has a guest; its status can't be changed.", code="room_occupied")
    old_status = room.operational_status
    if old_status == new_status:
        return _detail(db, room)
    room.operational_status = new_status
    audit_service.record(
        db, action="room.status_changed", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="room", entity_id=room.id,
        summary=f"Room {room.room_number}: {old_status} -> {new_status}",
        changes={"operational_status": [old_status, new_status]}, meta=meta,
    )
    db.commit()
    return _detail(db, room)
