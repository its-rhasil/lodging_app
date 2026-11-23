"""Room types and their rate table (P1-10, P4-2, DL-R17).

A rate is the price per period of one stay plan, for one occupancy.
One validator (validate_rate_set) serves create and update, and always checks the
final state: the new capacity together with the new rates (or the existing ones).
"""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.core.principal import Principal
from app.core.request_context import RequestMeta
from app.models import RoomType, RoomTypeRate, StayPlan
from app.service import audit_service

EDITABLE_FIELDS = ("name", "description", "capacity", "is_active")


def validate_rate_set(capacity: int, rates: list[dict], plans: dict[int, StayPlan]) -> None:
    """`rates`: dicts with stay_plan_id, occupancy, price. `plans`: this tenant's plans by id.

    - every plan must belong to the tenant (another tenant's plan reads as not found);
    - occupancy is 1..capacity;
    - one price per (plan, occupancy);
    - the daily plan has a price for every occupancy 1..capacity;
    - other plans are optional and may leave occupancies out.
    """
    unknown = sorted({r["stay_plan_id"] for r in rates} - plans.keys())
    if unknown:
        raise NotFound("Stay plan not found.", code="stay_plan_not_found", details={"stay_plan_ids": unknown})

    too_big = sorted({r["occupancy"] for r in rates if r["occupancy"] > capacity})
    if too_big:
        raise ValidationFailed(
            f"Occupancy can't be more than the capacity ({capacity}).",
            code="occupancy_exceeds_capacity", details={"occupancies": too_big},
        )

    keys = [(r["stay_plan_id"], r["occupancy"]) for r in rates]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ValidationFailed(
            "Each plan and occupancy can have only one price.", code="duplicate_rate",
            details={"rates": [{"stay_plan_id": p, "occupancy": o} for p, o in duplicates]},
        )

    daily = next(p for p in plans.values() if p.is_daily)
    covered = {o for p, o in keys if p == daily.id}
    missing = sorted(set(range(1, capacity + 1)) - covered)
    if missing:
        raise ValidationFailed(
            f"The {daily.name} plan needs a price for every occupancy from 1 to {capacity}.",
            code="daily_rates_incomplete", details={"stay_plan_id": daily.id, "missing_occupancies": missing},
        )


def _tenant_plans(db: Session, tenant_id: int) -> dict[int, StayPlan]:
    return {p.id: p for p in db.scalars(select(StayPlan).where(StayPlan.tenant_id == tenant_id))}


def _rates_for_audit(rates) -> list[str]:
    """Stable, JSON-safe form, e.g. 'plan 1 x2 = 1000.00' (audit changes can't hold Decimals)."""
    rows = [(r["stay_plan_id"], r["occupancy"], r["price"]) if isinstance(r, dict)
            else (r.stay_plan_id, r.occupancy, r.price) for r in rates]
    return [f"plan {p} x{o} = {price:.2f}" for p, o, price in sorted(rows)]


def _add_rates(db: Session, room_type: RoomType, rates: list[dict]) -> None:
    for r in rates:
        db.add(RoomTypeRate(
            tenant_id=room_type.tenant_id, room_type_id=room_type.id,
            stay_plan_id=r["stay_plan_id"], occupancy=r["occupancy"], price=r["price"],
        ))


def list_room_types(db: Session, principal: Principal) -> list[RoomType]:
    return list(db.scalars(
        select(RoomType).where(RoomType.tenant_id == principal.tenant_id).order_by(RoomType.name, RoomType.id)
    ))


def get_room_type(db: Session, tenant_id: int, room_type_id: int, *, lock: bool = False) -> RoomType:
    """A room type of this tenant. Another tenant's room type is reported as not found."""
    query = select(RoomType).where(RoomType.tenant_id == tenant_id, RoomType.id == room_type_id)
    if lock:
        query = query.with_for_update()
    room_type = db.scalars(query).first()
    if room_type is None:
        raise NotFound("Room type not found.", code="room_type_not_found")
    return room_type


def create_room_type(db: Session, principal: Principal, *, name: str, description: str | None,
                     capacity: int, rates: list[dict], meta: RequestMeta) -> RoomType:
    validate_rate_set(capacity, rates, _tenant_plans(db, principal.tenant_id))
    room_type = RoomType(
        tenant_id=principal.tenant_id, name=name.strip(),
        description=(description or "").strip() or None, capacity=capacity,
    )
    db.add(room_type)
    db.flush()  # a taken name fails here: uq_room_type_name_per_tenant -> 409 room_type_name_taken
    _add_rates(db, room_type, rates)
    db.flush()
    audit_service.record(
        db, action="room_type.created", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="room_type", entity_id=room_type.id, summary=f"Room-type: {room_type.name} · Created",
        changes={"name": [None, room_type.name], "capacity": [None, capacity],
                 "rates": [None, _rates_for_audit(rates)]},
        meta=meta,
    )
    db.commit()
    return room_type


def update_room_type(db: Session, principal: Principal, room_type_id: int, fields: dict, *,
                     meta: RequestMeta) -> RoomType:
    """`fields` holds only what the client sent (exclude_unset). `rates`, if sent, replaces all rates."""
    room_type = get_room_type(db, principal.tenant_id, room_type_id, lock=True)
    new_rates = fields.get("rates")
    if "name" in fields and fields["name"] is not None:
        fields["name"] = fields["name"].strip()
    if "description" in fields:
        # description is the one field that can be cleared (sent as null or "").
        fields["description"] = (fields["description"] or "").strip() or None
    fields = {k: v for k, v in fields.items()
              if k in EDITABLE_FIELDS and (v is not None or k == "description")}

    existing_rates = list(db.scalars(select(RoomTypeRate).where(RoomTypeRate.room_type_id == room_type.id)))
    final_capacity = fields.get("capacity", room_type.capacity)
    final_rates = new_rates if new_rates is not None else [
        {"stay_plan_id": r.stay_plan_id, "occupancy": r.occupancy, "price": r.price} for r in existing_rates
    ]
    validate_rate_set(final_capacity, final_rates, _tenant_plans(db, principal.tenant_id))

    changes = {k: [getattr(room_type, k), v] for k, v in fields.items() if getattr(room_type, k) != v}
    if new_rates is not None:
        before, after = _rates_for_audit(existing_rates), _rates_for_audit(new_rates)
        if before != after:
            changes["rates"] = [before, after]
            db.execute(delete(RoomTypeRate).where(RoomTypeRate.room_type_id == room_type.id))
            _add_rates(db, room_type, new_rates)
    if not changes:
        return room_type

    for key in EDITABLE_FIELDS:
        if key in changes:
            setattr(room_type, key, changes[key][1])
    db.flush()  # uq_room_type_name_per_tenant on a rename
    audit_service.record(
        db, action="room_type.updated", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="room_type", entity_id=room_type.id, summary=f"Room-type: {room_type.name} · Updated",
        changes=changes, meta=meta,
    )
    db.commit()
    return room_type
