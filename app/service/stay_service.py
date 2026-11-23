"""Check-in (P1-4, P1-6, P1-7, P4-3, P6-1) and the stay read model.

Check-in is one transaction (architecture.md §8.3). Lock order: room -> stay -> folio
(the stay and folio are new here, so only the room needs a lock).

Price (owner, 2026-11-16): listed_price is the rate-table price at check-in. The agreed
price may be lower (a discount, needs stay.override_rate, reason optional) but never higher.
"""
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.core.principal import Principal
from app.core.request_context import RequestMeta
from app.models import (
    Folio, FolioTransaction, Guest, Room, RoomTypeRate, Stay, StayPlan, StayRoomMove, TenantSettings,
)
from app.service import audit_service, guest_service, posting_service
from app.service.room_service import active_stay_ids, get_room
from app.service.room_type_service import get_room_type
from app.service.stay_plan_service import get_plan

# A check-in time a little ahead of the server clock is a clock difference, not a future booking.
CLOCK_TOLERANCE = timedelta(minutes=1)
# Even a manager can't backdate further than this: older is almost certainly a typo (owner, 2026-11-17).
MAX_BACKDATE = timedelta(days=30)
CENT = Decimal("0.01")


def discount_percent(listed: Decimal, agreed: Decimal) -> Decimal:
    """(listed - agreed) / listed x 100, rounded to 2 decimals. 1000 -> 850 gives 15.00."""
    return ((listed - agreed) / listed * 100).quantize(CENT, rounding=ROUND_HALF_UP)


def folio_balance(db: Session, folio_id: int) -> Decimal:
    """Debits minus credits (data-model.md §4.4). > 0 the guest owes; < 0 the guest is in credit."""
    signed = case((FolioTransaction.direction == "debit", FolioTransaction.amount),
                  else_=-FolioTransaction.amount)
    total = db.scalar(select(func.coalesce(func.sum(signed), 0)).where(FolioTransaction.folio_id == folio_id))
    return Decimal(total).quantize(CENT)


def get_stay(db: Session, tenant_id: int, stay_id: int, *, lock: bool = False) -> Stay:
    """A stay of this tenant. Another tenant's stay is reported as not found."""
    query = select(Stay).where(Stay.tenant_id == tenant_id, Stay.id == stay_id)
    if lock:
        # populate_existing: reload the values under the lock, even if this stay was loaded earlier.
        query = query.with_for_update().execution_options(populate_existing=True)
    stay = db.scalars(query).first()
    if stay is None:
        raise NotFound("Stay not found.", code="stay_not_found")
    return stay


def stay_out(db: Session, stay: Stay) -> dict:
    room_number = db.scalar(select(Room.room_number).where(Room.id == stay.room_id))
    plan_name = db.scalar(select(StayPlan.name).where(StayPlan.id == stay.stay_plan_id))
    guest = db.get(Guest, stay.guest_id)
    folio = db.scalars(select(Folio).where(Folio.stay_id == stay.id)).one()
    return {
        "id": stay.id, "status": stay.status, "room_id": stay.room_id, "room_number": room_number,
        "guest": guest, "stay_plan_id": stay.stay_plan_id, "stay_plan_name": plan_name,
        "occupancy": stay.occupancy, "period_hours": stay.period_hours, "grace_minutes": stay.grace_minutes,
        "actual_check_in_at": stay.actual_check_in_at, "expected_checkout_at": stay.expected_checkout_at,
        "actual_checkout_at": stay.actual_checkout_at,
        "listed_price": stay.listed_price, "agreed_price": stay.agreed_price,
        "discount_percent": discount_percent(stay.listed_price, stay.agreed_price),
        "folio": {"id": folio.id, "status": folio.status, "balance": folio_balance(db, folio.id)},
    }


def list_offers(db: Session, principal: Principal, room_id: int, occupancy: int) -> list[dict]:
    """Active plans this room's type has a rate for at this occupancy, with the listed price."""
    room = get_room(db, principal.tenant_id, room_id)
    rows = db.execute(
        select(StayPlan, RoomTypeRate.price)
        .join(RoomTypeRate, (RoomTypeRate.tenant_id == StayPlan.tenant_id)
              & (RoomTypeRate.stay_plan_id == StayPlan.id))
        .where(RoomTypeRate.tenant_id == principal.tenant_id, RoomTypeRate.room_type_id == room.room_type_id,
               RoomTypeRate.occupancy == occupancy, StayPlan.is_active.is_(True))
        .order_by(StayPlan.sort_order, StayPlan.id)
    ).all()
    return [
        {"stay_plan_id": plan.id, "name": plan.name, "period_hours": plan.period_hours,
         "grace_minutes": plan.grace_minutes, "is_daily": plan.is_daily, "listed_price": price}
        for plan, price in rows
    ]


def _check_room_available(db: Session, room: Room) -> None:
    if not room.is_active:
        raise Conflict("This room is inactive.", code="room_inactive")
    if active_stay_ids(db, room.tenant_id, [room.id]):
        raise Conflict("This room already has a guest.", code="room_occupied")
    if room.operational_status != "available":
        raise Conflict(f"This room is not available (currently {room.operational_status}).",
                       code="room_not_available", details={"status": room.operational_status})


def _resolve_price(principal: Principal, listed: Decimal, agreed: Decimal | None) -> Decimal:
    if agreed is None:
        return listed
    if agreed > listed:
        raise ValidationFailed("The agreed price can't be more than the listed price.",
                               code="price_above_listed", details={"listed_price": str(listed)})
    if agreed < listed and not principal.has("stay.override_rate"):
        raise PermissionDenied("You don't have permission to give a discount.",
                               code="override_rate_not_allowed", details={"permission": "stay.override_rate"})
    return agreed


def _resolve_check_in_time(db: Session, principal: Principal, requested: datetime | None,
                           reason: str | None, now: datetime) -> datetime:
    if requested is None:
        return now
    if requested > now + CLOCK_TOLERANCE:
        raise ValidationFailed("The check-in time can't be in the future.", code="check_in_in_future")
    if now - requested > MAX_BACKDATE:
        raise ValidationFailed("The check-in time is more than 30 days ago. Check the date.",
                               code="check_in_too_old")
    window = db.scalar(select(TenantSettings.max_backdate_minutes)
                       .where(TenantSettings.tenant_id == principal.tenant_id))
    if now - requested > timedelta(minutes=window):
        if not principal.has("stay.backdate"):
            raise PermissionDenied(f"Only a manager can backdate a check-in by more than {window} minutes.",
                                   code="backdate_not_allowed", details={"permission": "stay.backdate"})
        if not reason:
            raise ValidationFailed("A reason is required to backdate this far.", code="reason_required",
                                   details={"field": "backdate_reason"})
    return requested


def check_in(db: Session, principal: Principal, *, room_id: int, stay_plan_id: int, occupancy: int,
             guest_id: int | None, guest: dict | None, agreed_price: Decimal | None, rate_reason: str | None,
             check_in_at: datetime | None, backdate_reason: str | None,
             expected_checkout_at: datetime | None, now: datetime, meta: RequestMeta) -> dict:
    tenant_id = principal.tenant_id
    rate_reason = (rate_reason or "").strip() or None
    backdate_reason = (backdate_reason or "").strip() or None

    # 1. Lock the room first, then check it (a status change or another check-in waits for us).
    room = get_room(db, tenant_id, room_id, lock=True)
    _check_room_available(db, room)

    # 2. Plan and occupancy.
    plan = get_plan(db, tenant_id, stay_plan_id)
    if not plan.is_active:
        raise ValidationFailed("This stay plan is inactive.", code="stay_plan_inactive")
    room_type = get_room_type(db, tenant_id, room.room_type_id)
    if occupancy > room_type.capacity:
        raise ValidationFailed(f"This room takes at most {room_type.capacity} guests.",
                               code="occupancy_exceeds_capacity", details={"capacity": room_type.capacity})

    # 3. Price: listed from the rate table; agreed may be a discount, never more.
    listed = db.scalar(select(RoomTypeRate.price).where(
        RoomTypeRate.room_type_id == room_type.id, RoomTypeRate.stay_plan_id == plan.id,
        RoomTypeRate.occupancy == occupancy,
    ))
    if listed is None:
        raise ValidationFailed(f"{plan.name} isn't offered for this room at {occupancy} guest(s).",
                               code="plan_not_offered")
    agreed = _resolve_price(principal, listed, agreed_price)

    # 4. Time.
    checked_in_at = _resolve_check_in_time(db, principal, check_in_at, backdate_reason, now)
    if expected_checkout_at is not None and expected_checkout_at <= checked_in_at:
        raise ValidationFailed("Expected checkout must be after check-in.", code="invalid_expected_checkout")

    # 5. Guest: reuse by id, or create.
    if guest_id is not None:
        guest_row = guest_service.get_guest(db, tenant_id, guest_id)
    else:
        guest_row = guest_service.create_guest(db, tenant_id, **guest)

    # 6. Stay (plan snapshot copied) and its folio.
    stay = Stay(
        tenant_id=tenant_id, room_id=room.id, guest_id=guest_row.id, stay_plan_id=plan.id, status="active",
        actual_check_in_at=checked_in_at, expected_checkout_at=expected_checkout_at,
        listed_price=listed, agreed_price=agreed, occupancy=occupancy,
        period_hours=plan.period_hours, grace_minutes=plan.grace_minutes,
        created_by_user_id=principal.user_id,
    )
    db.add(stay)
    db.flush()  # backstop: uq_one_active_stay_per_room -> 409 room_occupied
    folio = Folio(tenant_id=tenant_id, stay_id=stay.id, opened_at=now)
    db.add(folio)
    db.flush()

    # 7. Period 1 (and any periods already due for a backdated check-in).
    posting_service.post_due_room_charges(db, folio, stay, now)

    # 8. Audit, then the single commit.
    discount = discount_percent(listed, agreed)
    reasons = [f"Discount: {rate_reason}" if rate_reason else None,
               f"Backdated: {backdate_reason}" if backdate_reason else None]
    audit_service.record(
        db, action="stay.checked_in", actor=principal.actor, tenant_id=tenant_id,
        entity_type="stay", entity_id=stay.id,
        summary=f"Room {room.room_number} · Checked in {guest_row.full_name} · {plan.name}",
        changes={
            "room_id": [None, room.id], "guest_id": [None, guest_row.id], "stay_plan_id": [None, plan.id],
            "occupancy": [None, occupancy], "listed_price": [None, str(listed)],
            "agreed_price": [None, str(agreed)], "discount_percent": [None, str(discount)],
            "actual_check_in_at": [None, checked_in_at.isoformat()],
            "guest_created": [None, guest_id is None],
        },
        reason="; ".join(r for r in reasons if r) or None, meta=meta,
    )
    db.commit()
    return stay_out(db, stay)


# --- Day 3: checkout and extend ------------------------------------------------

def lock_stay_and_room(db: Session, tenant_id: int, stay_id: int) -> tuple[Stay, Room]:
    """Lock order rooms -> stay (architecture.md §10): read the stay, lock its room, then the stay.

    If a room change moved the stay while we waited for the room lock, the caller retries.
    """
    stay = get_stay(db, tenant_id, stay_id)
    room = get_room(db, tenant_id, stay.room_id, lock=True)
    stay = get_stay(db, tenant_id, stay_id, lock=True)
    if stay.room_id != room.id:
        raise Conflict("The stay changed while you were working. Please try again.", code="stay_changed")
    return stay, room


def lock_folio(db: Session, stay: Stay) -> Folio:
    return db.scalars(
        select(Folio)
        .where(Folio.stay_id == stay.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def _resolve_checkout_time(db: Session, principal: Principal, stay: Stay, requested: datetime | None,
                           reason: str | None, now: datetime) -> datetime:
    """When the guest left: `requested`, else now (owner, 2026-11-23)."""
    if requested is None:
        return now
    if requested > now + CLOCK_TOLERANCE:
        raise ValidationFailed("The checkout time can't be in the future.", code="checkout_in_future")
    if requested <= stay.actual_check_in_at:
        raise ValidationFailed("The checkout time must be after the check-in time.",
                               code="checkout_before_check_in")
    if now - requested > MAX_BACKDATE:
        raise ValidationFailed("The checkout time is more than 30 days ago. Check the date.",
                               code="checkout_too_old")

    # The guest can't have left before their last room change or conversion to full day.
    last_move = db.scalar(
        select(func.max(StayRoomMove.moved_at))
        .where(StayRoomMove.tenant_id == stay.tenant_id, StayRoomMove.stay_id == stay.id)
    )
    for changed_at in (last_move, stay.converted_at):
        if changed_at is not None and requested < changed_at:
            raise ValidationFailed("The guest changed room or plan after this time. Pick a later time.",
                                   code="checkout_before_last_change")

    # Same rule as a backdated check-in: further back than the window needs a manager and a reason.
    window = db.scalar(select(TenantSettings.max_backdate_minutes)
                       .where(TenantSettings.tenant_id == principal.tenant_id))
    if now - requested > timedelta(minutes=window):
        if not principal.has("stay.backdate"):
            raise PermissionDenied(f"Only a manager can backdate a checkout by more than {window} minutes.",
                                   code="backdate_not_allowed", details={"permission": "stay.backdate"})
        if not reason:
            raise ValidationFailed("A reason is required to backdate this far.", code="reason_required",
                                   details={"field": "backdate_reason"})
    return min(requested, now)  # a few seconds ahead (clock difference) counts as now


def _room_charges_after(db: Session, folio: Folio, stay: Stay, left_at: datetime) -> list[FolioTransaction]:
    """Live room charges for periods that weren't due yet when the guest left.

    They exist when someone opened the stay after the guest left and a new period fell due.
    """
    due = posting_service.periods_due(stay.actual_check_in_at, left_at, stay.period_hours, stay.grace_minutes)
    reversed_ids = select(FolioTransaction.related_txn_id).where(
        FolioTransaction.folio_id == folio.id,
        FolioTransaction.txn_type == "reversal",
    )
    return list(db.scalars(
        select(FolioTransaction)
        .where(
            FolioTransaction.folio_id == folio.id,
            FolioTransaction.txn_type == "room_charge",
            FolioTransaction.posting_key.startswith(f"room:{stay.stay_plan_id}:"),
            FolioTransaction.period_no > due,
            FolioTransaction.id.not_in(reversed_ids),
        )
        .order_by(FolioTransaction.period_no)
    ))


def checkout(db: Session, principal: Principal, stay_id: int, *, force_reason: str | None,
             checkout_at: datetime | None = None, backdate_reason: str | None = None,
             now: datetime, meta: RequestMeta) -> dict:
    """DL-P08: post due charges, then settle. 0 -> close the folio; owed -> forced checkout
    (folio.close_with_balance + reason, folio stays open); in credit -> refund first.
    checkout_at: when the guest actually left (default now); charges stop there."""
    stay, room = lock_stay_and_room(db, principal.tenant_id, stay_id)
    if stay.status != "active":
        raise Conflict("This stay is already checked out.", code="stay_not_active")
    backdate_reason = (backdate_reason or "").strip() or None
    left_at = _resolve_checkout_time(db, principal, stay, checkout_at, backdate_reason, now)
    folio = lock_folio(db, stay)

    # Charges stop when the guest left, not when the desk pressed the button.
    posting_service.post_due_room_charges(db, folio, stay, left_at)
    late = _room_charges_after(db, folio, stay, left_at)
    if late:
        names = ", ".join(t.description for t in late)
        raise Conflict(f"The bill has room charges for after the guest left ({names}). "
                       "Reverse them, then check out again.",
                       code="charges_after_checkout", details={"transaction_ids": [t.id for t in late]})
    balance = folio_balance(db, folio.id)
    force_reason = (force_reason or "").strip() or None

    if balance < 0:
        raise Conflict(f"The guest is owed {-balance}. Record a refund first.",
                       code="refund_required", details={"balance": str(balance)})
    if balance > 0:
        if not principal.has("folio.close_with_balance"):
            raise PermissionDenied(f"The guest owes {balance}. Take the payment, you don't have the permission to check out.",
                                   code="balance_outstanding", details={"balance": str(balance)})
        if not force_reason:
            raise ValidationFailed("A reason is required to check out with a balance owed.",
                                   code="reason_required", details={"balance": str(balance)})
        folio.forced_checkout_reason = force_reason  # folio stays open: listed under Pending balances
    else:
        folio.status = "closed"
        folio.closed_at = now
        folio.closed_by_user_id = principal.user_id

    stay.status = "checked_out"
    stay.actual_checkout_at = left_at
    room.operational_status = "cleaning"

    reasons = [force_reason, f"Backdated: {backdate_reason}" if backdate_reason else None]
    audit_service.record(
        db, action="stay.checked_out", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="stay", entity_id=stay.id,
        summary=f"Room {room.room_number} · Checked out {stay.guest.full_name} · {stay.stay_plan.name}" + (f", Pending: {balance}" if balance > 0 else ""),
        changes={"status": ["active", "checked_out"], "balance": [None, str(balance)],
                 "folio_status": ["open", folio.status],
                 "actual_checkout_at": [None, left_at.isoformat()]},
        reason="; ".join(r for r in reasons if r) or None, meta=meta,
    )

    db.commit()
    return stay_out(db, stay)


def change_room(db: Session, principal: Principal, stay_id: int, *, new_room_id: int,
                agreed_price: Decimal | None, rate_reason: str | None, reason: str | None,
                now: datetime, meta: RequestMeta) -> dict:
    """Room change in place (DL-R13, DL-R23). The stay keeps its folio, plan and clock."""
    tenant_id = principal.tenant_id
    stay = get_stay(db, tenant_id, stay_id)
    if new_room_id == stay.room_id:
        raise ValidationFailed("The guest is already in this room.", code="same_room")

    # 1. Lock both rooms in ascending id order, then the stay (architecture.md §10).
    first_id, second_id = sorted([stay.room_id, new_room_id])
    rooms = {
        first_id: get_room(db, tenant_id, first_id, lock=True),
        second_id: get_room(db, tenant_id, second_id, lock=True),
    }
    old_room_id = stay.room_id
    stay = get_stay(db, tenant_id, stay_id, lock=True)
    if stay.room_id != old_room_id:
        raise Conflict("The stay changed while you were working. Please try again.", code="stay_changed")
    if stay.status != "active":
        raise Conflict("This stay is already checked out.", code="stay_not_active")
    old_room, new_room = rooms[old_room_id], rooms[new_room_id]

    # 2. The new room must be free, fit the guests, and offer the stay's plan.
    _check_room_available(db, new_room)
    new_type = get_room_type(db, tenant_id, new_room.room_type_id)
    if stay.occupancy > new_type.capacity:
        raise ValidationFailed(f"That room takes at most {new_type.capacity} guests.",
                               code="occupancy_exceeds_capacity", details={"capacity": new_type.capacity})
    listed = db.scalar(select(RoomTypeRate.price).where(
        RoomTypeRate.room_type_id == new_type.id,
        RoomTypeRate.stay_plan_id == stay.stay_plan_id,
        RoomTypeRate.occupancy == stay.occupancy,
    ))
    if listed is None:
        raise ValidationFailed("That room doesn't offer this stay's plan for this many guests.",
                               code="plan_not_offered")
    agreed = _resolve_price(principal, listed, agreed_price)

    # 3. Post everything due at the OLD price before the price changes (DL-R21).
    folio = lock_folio(db, stay)
    posting_service.post_due_room_charges(db, folio, stay, now)

    # 4. Record the move and update the stay in place.
    db.add(StayRoomMove(
        tenant_id=tenant_id, stay_id=stay.id, from_room_id=old_room.id, to_room_id=new_room.id,
        rate_before=stay.agreed_price, rate_after=agreed, moved_at=now,
        moved_by_user_id=principal.user_id, reason=(reason or "").strip() or None,
    ))
    old_prices = (str(stay.listed_price), str(stay.agreed_price))
    stay.room_id = new_room.id
    stay.listed_price = listed
    stay.agreed_price = agreed
    old_room.operational_status = "cleaning"
    db.flush()  # backstop: uq_one_active_stay_per_room -> 409 room_occupied

    audit_service.record(
        db, action="stay.room_changed", actor=principal.actor, tenant_id=tenant_id,
        entity_type="stay", entity_id=stay.id,
        summary=f"Room {old_room.room_number} → {new_room.room_number} · {stay.guest.full_name}",
        changes={"room_id": [old_room.id, new_room.id],
                 "listed_price": [old_prices[0], str(listed)],
                 "agreed_price": [old_prices[1], str(agreed)],
                 "rate_reason": [None, (rate_reason or "").strip() or None]},
        reason=(reason or "").strip() or None, meta=meta,
    )
    db.commit()
    return stay_out(db, stay)


def extend(db: Session, principal: Principal, stay_id: int, *, expected_checkout_at: datetime,
           meta: RequestMeta) -> dict:
    """Informational only: posting continues while the stay is active, whatever this says."""
    stay = get_stay(db, principal.tenant_id, stay_id, lock=True)
    if stay.status != "active":
        raise Conflict("This stay is already checked out.", code="stay_not_active")
    if expected_checkout_at <= stay.actual_check_in_at:
        raise ValidationFailed("Expected checkout must be after check-in.", code="invalid_expected_checkout")

    old = stay.expected_checkout_at
    stay.expected_checkout_at = expected_checkout_at
    audit_service.record(
        db, action="stay.extended", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="stay", entity_id=stay.id, summary=f"Room {stay.room.room_number} · Extend Stay · {stay.guest.full_name}",
        changes={"expected_checkout_at": [old.isoformat() if old else None, expected_checkout_at.isoformat()]},
        meta=meta,
    )
    db.commit()
    return stay_out(db, stay)
