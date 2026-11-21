"""Folio operations (architecture.md §8.3, P4-5; owner decisions 2026-11-16).

Every operation:
1. finds the stay (this tenant only) and locks its folio (FOR UPDATE);
2. posts due room charges first, so the balance it decides on is current;
3. checks the folio state:
   - stay active:                      everything allowed;
   - stay checked out, folio open:     payments up to the amount owed, waivers, reversals;
   - folio closed:                     nothing;
4. checks its own rule, inserts one ledger row, writes one audit row, commits once.
A checked-out stay's folio closes itself when its balance reaches 0.
"""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.models import Folio, FolioTransaction, RoomTypeRate, StayPlan
from app.service import audit_service, posting_service
from app.service.room_type_service import get_room_type
from app.service.stay_service import (
    _resolve_price, folio_balance, get_stay, lock_folio, lock_stay_and_room, stay_out,
)

CHARGE_TYPES = ("room_charge", "charge")


# --- loading and state -------------------------------------------------------

def _open_folio(db, principal, stay_id, now):
    """Lock the stay's folio and post due room charges. Returns (stay, folio)."""
    stay = get_stay(db, principal.tenant_id, stay_id)
    folio = db.scalars(
        select(Folio).where(Folio.stay_id == stay.id).with_for_update()
    ).one()
    posting_service.post_due_room_charges(db, folio, stay, now)
    return stay, folio


def _require_open(folio):
    if folio.status == "closed":
        raise Conflict("This folio is closed.", code="folio_closed")


def _require_active_stay(stay):
    if stay.status != "active":
        raise Conflict("Only allowed while the guest is staying.", code="stay_not_active")


def _close_if_settled(db, stay, folio, now):
    """A checked-out guest's folio closes itself once nothing is owed (DL-P08)."""
    if stay.status == "checked_out" and folio_balance(db, folio.id) == 0:
        folio.status = "closed"
        folio.closed_at = now
        folio.closed_by_user_id = None  # NULL = closed automatically


def _clean_reason(reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed("A reason is required.", code="reason_required")
    return reason


def _transactions(db, folio_id):
    return list(db.scalars(
        select(FolioTransaction)
        .where(FolioTransaction.folio_id == folio_id)
        .order_by(FolioTransaction.id)
    ))


def _get_transaction(db, folio, txn_id):
    """A row of this folio. A row of another folio (or tenant) is reported as not found."""
    txn = db.scalars(
        select(FolioTransaction).where(
            FolioTransaction.folio_id == folio.id,
            FolioTransaction.id == txn_id,
        )
    ).first()
    if txn is None:
        raise NotFound("Transaction not found.", code="transaction_not_found")
    return txn


# --- waiver / reversal bookkeeping -------------------------------------------

def _reversed_ids(txns):
    return {t.related_txn_id for t in txns if t.txn_type == "reversal"}


def _live_waivers(txns, charge_id):
    """Waivers on this charge that haven't themselves been reversed."""
    reversed_ids = _reversed_ids(txns)
    return [
        t for t in txns
        if t.txn_type == "waiver" and t.related_txn_id == charge_id and t.id not in reversed_ids
    ]


def _waivable_amount(txns, charge):
    if charge.id in _reversed_ids(txns):
        return Decimal("0.00")
    waived = sum((w.amount for w in _live_waivers(txns, charge.id)), Decimal("0.00"))
    return charge.amount - waived


# --- read model --------------------------------------------------------------

def folio_out(db, folio):
    txns = _transactions(db, folio.id)
    # One pass for the bookkeeping, so a long folio stays fast (no re-scan per charge).
    reversed_ids = _reversed_ids(txns)
    waived: dict[int, Decimal] = {}
    for t in txns:
        if t.txn_type == "waiver" and t.id not in reversed_ids:
            waived[t.related_txn_id] = waived.get(t.related_txn_id, Decimal("0.00")) + t.amount

    def waivable(charge):
        if charge.id in reversed_ids:
            return Decimal("0.00")
        return charge.amount - waived.get(charge.id, Decimal("0.00"))

    rows = []
    for t in txns:
        rows.append({
            "id": t.id,
            "txn_type": t.txn_type,
            "direction": t.direction,
            "amount": t.amount,
            "description": t.description,
            "period_no": t.period_no,
            "period_start_at": t.period_start_at,
            "payment_method": t.payment_method,
            "reference": t.reference,
            "related_txn_id": t.related_txn_id,
            "reason": t.reason,
            "created_by_user_id": t.created_by_user_id,
            "created_at": t.created_at,
            "is_reversed": t.id in reversed_ids,
            "waivable_amount": waivable(t) if t.txn_type in CHARGE_TYPES else None,
        })
    return {
        "id": folio.id,
        "stay_id": folio.stay_id,
        "status": folio.status,
        "balance": folio_balance(db, folio.id),
        "transactions": rows,
    }


def _add(db, folio, principal, **fields):
    txn = FolioTransaction(
        tenant_id=folio.tenant_id,
        folio_id=folio.id,
        created_by_user_id=principal.user_id,
        **fields,
    )
    db.add(txn)
    db.flush()
    return txn


def _audit(db, principal, meta, action, folio, txn, summary, reason=None):
    audit_service.record(
        db, action=action, actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="folio", entity_id=folio.id, summary=summary,
        changes={"transaction_id": [None, txn.id], "amount": [None, str(txn.amount)]},
        reason=reason, meta=meta,
    )


# --- operations --------------------------------------------------------------

def view_folio(db, principal, stay_id, *, now):
    """Opening the folio posts due room charges (owner decision 2026-11-16)."""
    stay, folio = _open_folio(db, principal, stay_id, now)
    db.commit()
    return folio_out(db, folio)


def post_charge(db, principal, stay_id, *, amount, description, now, meta):
    stay, folio = _open_folio(db, principal, stay_id, now)
    _require_open(folio)
    _require_active_stay(stay)

    txn = _add(db, folio, principal, txn_type="charge", direction="debit",
               amount=amount, description=description.strip())
    _audit(db, principal, meta, "folio.charge_posted", folio, txn, f"Charge {amount}: {txn.description}")
    db.commit()
    return folio_out(db, folio)


def record_payment(db, principal, stay_id, *, amount, method, reference, idempotency_key, now, meta):
    """Returns (folio, created). A repeated key returns the original payment (created=False)."""
    stay, folio = _open_folio(db, principal, stay_id, now)

    # Double submit: same key on this folio -> the payment already exists.
    posting_key = f"pay:{idempotency_key}"
    existing = db.scalars(
        select(FolioTransaction).where(
            FolioTransaction.folio_id == folio.id,
            FolioTransaction.posting_key == posting_key,
        )
    ).first()
    if existing is not None:
        if existing.amount != amount or existing.payment_method != method:
            raise Conflict("This payment key was already used for a different payment.",
                           code="idempotency_key_reused")
        db.commit()  # keep any room charges the catch-up just posted
        return folio_out(db, folio), False

    _require_open(folio)
    if stay.status == "checked_out":
        owed = folio_balance(db, folio.id)
        if amount > owed:
            raise ValidationFailed(f"The guest owes {owed}; the payment can't be more.",
                                   code="amount_exceeds_balance")

    txn = _add(db, folio, principal, txn_type="payment", direction="credit", amount=amount,
               payment_method=method, reference=(reference or "").strip() or None,
               posting_key=posting_key)
    _close_if_settled(db, stay, folio, now)
    _audit(db, principal, meta, "payment.recorded", folio, txn, f"Payment {amount} by {method}")
    db.commit()
    return folio_out(db, folio), True


def record_refund(db, principal, stay_id, *, amount, method, reference, reason, now, meta):
    stay, folio = _open_folio(db, principal, stay_id, now)
    _require_open(folio)
    _require_active_stay(stay)
    reason = _clean_reason(reason)

    credit = -folio_balance(db, folio.id)
    if amount > credit:
        raise ValidationFailed(f"The guest is owed {max(credit, Decimal('0.00'))}; the refund can't be more.",
                               code="refund_exceeds_credit")

    txn = _add(db, folio, principal, txn_type="refund", direction="debit", amount=amount,
               payment_method=method, reference=(reference or "").strip() or None, reason=reason)
    _audit(db, principal, meta, "payment.refunded", folio, txn, f"Refund {amount} by {method}", reason)
    db.commit()
    return folio_out(db, folio)


def waive(db, principal, stay_id, txn_id, *, amount, reason, now, meta):
    stay, folio = _open_folio(db, principal, stay_id, now)
    _require_open(folio)
    reason = _clean_reason(reason)

    charge = _get_transaction(db, folio, txn_id)
    if charge.txn_type not in CHARGE_TYPES:
        raise ValidationFailed("Only charges can be waived.", code="not_waivable")
    txns = _transactions(db, folio.id)
    if charge.id in _reversed_ids(txns):
        raise Conflict("This charge was reversed.", code="already_reversed")
    waivable = _waivable_amount(txns, charge)
    if amount > waivable:
        raise ValidationFailed(f"At most {waivable} of this charge can be waived.",
                               code="waiver_exceeds_remaining", details={"waivable_amount": str(waivable)})

    txn = _add(db, folio, principal, txn_type="waiver", direction="credit", amount=amount,
               related_txn_id=charge.id, reason=reason)
    _close_if_settled(db, stay, folio, now)
    _audit(db, principal, meta, "folio.waived", folio, txn, f"Waived {amount} of transaction {charge.id}", reason)
    db.commit()
    return folio_out(db, folio)


def reverse(db, principal, stay_id, txn_id, *, reason, now, meta):
    stay, folio = _open_folio(db, principal, stay_id, now)
    _require_open(folio)
    reason = _clean_reason(reason)

    original = _get_transaction(db, folio, txn_id)
    if original.txn_type == "reversal":
        raise ValidationFailed("A reversal can't be reversed.", code="cannot_reverse_reversal")
    txns = _transactions(db, folio.id)
    if original.id in _reversed_ids(txns):
        raise Conflict("This transaction was already reversed.", code="already_reversed")
    waivers = _live_waivers(txns, original.id)
    if waivers:
        raise Conflict("Reverse the waivers on this charge first.", code="reverse_waivers_first",
                       details={"waiver_ids": [w.id for w in waivers]})

    opposite = "credit" if original.direction == "debit" else "debit"
    txn = _add(db, folio, principal, txn_type="reversal", direction=opposite, amount=original.amount,
               related_txn_id=original.id, reason=reason)
    _close_if_settled(db, stay, folio, now)
    _audit(db, principal, meta, "folio.reversed", folio, txn, f"Reversed transaction {original.id}", reason)
    db.commit()
    return folio_out(db, folio)


# --- cancel a check-in (owner, 2026-11-18) ---------------------------------------------------

CANCEL_WINDOW = timedelta(minutes=30)


def cancel_stay(db, principal, stay_id, *, reason, now, meta):
    """Undo a check-in made by mistake (wrong room, wrong guest, guest changed their mind).

    - The desk (stay.check_in) may cancel within 30 minutes of entering the check-in;
      after that only a manager (folio.reverse).
    - Refused while a payment stands: money taken must be reversed or refunded first.
    - Every live charge is reversed (its live waivers first), so the bill nets to 0 and closes.
    - The stay becomes 'cancelled' (no more posting); the room is available again.
    """
    tenant_id = principal.tenant_id
    reason = _clean_reason(reason)
    stay, room = lock_stay_and_room(db, tenant_id, stay_id)
    if stay.status != "active":
        raise Conflict("Only a guest who is still checked in can be cancelled.", code="stay_not_active")
    folio = lock_folio(db, stay)
    if now - folio.opened_at > CANCEL_WINDOW and not principal.has("folio.reverse"):
        raise PermissionDenied("More than 30 minutes since check-in: ask a manager to cancel it.",
                               code="cancel_window_passed", details={"permission": "folio.reverse"})

    txns = _transactions(db, folio.id)
    reversed_ids = _reversed_ids(txns)
    live = [t for t in txns if t.id not in reversed_ids and t.txn_type != "reversal"]
    paid = sum((t.amount for t in live if t.txn_type == "payment"), Decimal("0.00"))
    refunded = sum((t.amount for t in live if t.txn_type == "refund"), Decimal("0.00"))
    if paid - refunded > 0:
        raise Conflict(f"A payment of {paid - refunded} was taken. Reverse it (if taken by mistake) "
                       "or refund it before cancelling.", code="payment_taken",
                       details={"paid": str(paid - refunded)})

    charges = [t for t in live if t.txn_type in CHARGE_TYPES]
    for charge in charges:
        for waiver in _live_waivers(txns, charge.id):
            _add(db, folio, principal, txn_type="reversal", direction="debit", amount=waiver.amount,
                 related_txn_id=waiver.id, reason=reason)
        _add(db, folio, principal, txn_type="reversal", direction="credit", amount=charge.amount,
             related_txn_id=charge.id, reason=reason)

    stay.status = "cancelled"
    stay.actual_checkout_at = now
    folio.status = "closed"
    folio.closed_at = now
    folio.closed_by_user_id = principal.user_id
    room.operational_status = "available"

    audit_service.record(
        db, action="stay.cancelled", actor=principal.actor, tenant_id=tenant_id,
        entity_type="stay", entity_id=stay.id, summary=f"Cancelled the check-in in room {room.room_number}",
        changes={"status": ["active", "cancelled"], "reversed_charges": [None, [c.id for c in charges]]},
        reason=reason, meta=meta,
    )
    db.commit()
    return stay_out(db, stay)


# --- price correction (owner feedback, 2026-11-18) ----------------------------------------

def correct_price(db, principal, stay_id, *, agreed_price, reason, now, meta):
    """Fix a wrong agreed price (e.g. 8 typed instead of 800) on an active stay.

    A plain reversal can't do this: a reversed room charge is never posted again. So:
    1. post what is due (at the wrong price);
    2. every live room charge of the current plan at the wrong price is reversed (its live
       waivers first) and posted again at the right price, same period and start time;
    3. the stay's agreed price becomes the right one, so later periods use it.
    Same price rules as check-in: never above listed; lower needs stay.override_rate.
    """
    tenant_id = principal.tenant_id
    reason = _clean_reason(reason)
    stay, _room = lock_stay_and_room(db, tenant_id, stay_id)
    if stay.status != "active":
        raise Conflict("Only an active stay's price can be corrected.", code="stay_not_active")
    new_price = _resolve_price(principal, stay.listed_price, agreed_price)
    old_price = stay.agreed_price
    if new_price == old_price:
        raise ValidationFailed("That is already the price.", code="price_unchanged")

    folio = lock_folio(db, stay)
    posting_service.post_due_room_charges(db, folio, stay, now)
    txns = _transactions(db, folio.id)
    reversed_ids = _reversed_ids(txns)
    wrong = [
        t for t in txns
        if t.txn_type == "room_charge"
        and t.posting_key.startswith(f"room:{stay.stay_plan_id}:")
        and t.id not in reversed_ids
        and t.amount == old_price
    ]
    for charge in wrong:
        for waiver in _live_waivers(txns, charge.id):
            _add(db, folio, principal, txn_type="reversal", direction="debit", amount=waiver.amount,
                 related_txn_id=waiver.id, reason=reason)
        _add(db, folio, principal, txn_type="reversal", direction="credit", amount=charge.amount,
             related_txn_id=charge.id, reason=reason)
        _add(db, folio, principal, txn_type="room_charge", direction="debit", amount=new_price,
             description=f"{charge.description} (price corrected)",
             posting_key=f"{posting_service.room_posting_key(stay.stay_plan_id, charge.period_no)}:c{charge.id}",
             period_no=charge.period_no, period_start_at=charge.period_start_at)

    stay.agreed_price = new_price
    audit_service.record(
        db, action="stay.price_corrected", actor=principal.actor, tenant_id=tenant_id,
        entity_type="stay", entity_id=stay.id, summary=f"Price corrected from {old_price} to {new_price}",
        changes={"agreed_price": [str(old_price), str(new_price)],
                 "reposted_charges": [None, [c.id for c in wrong]]},
        reason=reason, meta=meta,
    )
    db.commit()
    return stay_out(db, stay)


# --- conversion (Day 3) ------------------------------------------------------------

def convert_to_daily(db, principal, stay_id, *, agreed_price, rate_reason, now, meta):
    """Short stay -> full day (DL-R10, DL-R23).

    The short-stay room charges are reversed (their live waivers first), the stay switches to
    the daily plan, and daily period 1 is posted. The clock keeps the original check-in.
    Example: fresh-up 2h at 500 from 14:00, converted at 19:30 to Full day at 1200:
    blocks 1-3 (1500) are reversed, day 1 (1200) is posted, day 2 is due tomorrow 14:30.
    """
    tenant_id = principal.tenant_id
    stay, room = lock_stay_and_room(db, tenant_id, stay_id)
    if stay.status != "active":
        raise Conflict("This stay is already checked out.", code="stay_not_active")

    daily = db.scalars(select(StayPlan).where(StayPlan.tenant_id == tenant_id, StayPlan.is_daily.is_(True))).one()
    old_plan_id = stay.stay_plan_id
    if old_plan_id == daily.id:
        raise ValidationFailed("This stay is already on the full-day plan.", code="already_daily")

    # Price: the daily listed price for this room and occupancy; lower is a discount.
    room_type = get_room_type(db, tenant_id, room.room_type_id)
    listed = db.scalar(select(RoomTypeRate.price).where(
        RoomTypeRate.room_type_id == room_type.id,
        RoomTypeRate.stay_plan_id == daily.id,
        RoomTypeRate.occupancy == stay.occupancy,
    ))
    if listed is None:
        raise ValidationFailed(f"This room has no {daily.name} price for {stay.occupancy} guest(s).",
                               code="plan_not_offered")
    agreed = _resolve_price(principal, listed, agreed_price)

    # Post what is due on the short plan, then reverse all of its room charges.
    folio = lock_folio(db, stay)
    posting_service.post_due_room_charges(db, folio, stay, now)
    reason = f"Converted to {daily.name}"
    txns = _transactions(db, folio.id)
    reversed_ids = _reversed_ids(txns)
    short_charges = [
        t for t in txns
        if t.txn_type == "room_charge"
        and t.posting_key.startswith(f"room:{old_plan_id}:")
        and t.id not in reversed_ids
    ]
    for charge in short_charges:
        for waiver in _live_waivers(txns, charge.id):
            _add(db, folio, principal, txn_type="reversal", direction="debit", amount=waiver.amount,
                 related_txn_id=waiver.id, reason=reason)
        _add(db, folio, principal, txn_type="reversal", direction="credit", amount=charge.amount,
             related_txn_id=charge.id, reason=reason)

    # Switch the stay to the daily plan; the clock stays at the original check-in.
    stay.converted_from_plan_id = old_plan_id
    stay.converted_at = now
    stay.stay_plan_id = daily.id
    stay.period_hours = daily.period_hours
    stay.grace_minutes = daily.grace_minutes
    stay.listed_price = listed
    stay.agreed_price = agreed
    db.flush()
    posting_service.post_due_room_charges(db, folio, stay, now)  # room:<daily>:1

    audit_service.record(
        db, action="stay.converted", actor=principal.actor, tenant_id=tenant_id,
        entity_type="stay", entity_id=stay.id, summary=f"Converted to {daily.name}",
        changes={"stay_plan_id": [old_plan_id, daily.id],
                 "agreed_price": [None, str(agreed)],
                 "reversed_charges": [None, [c.id for c in short_charges]],
                 "rate_reason": [None, (rate_reason or "").strip() or None]},
        meta=meta,
    )
    db.commit()
    return stay_out(db, stay)
