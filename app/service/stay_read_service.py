"""Read side for stays (P2-5): lists with balances, stay detail, catch-up posting for lists.

Screens that show balances post due room charges first (DL-R21): the stay detail, the
active-stays list, the pending-balances list and the dashboard. Those GETs therefore commit.
Balances for a list come from one grouped query, not one query per stay.
"""
from decimal import Decimal

from sqlalchemy import case, func, select

from app.models import Folio, FolioTransaction, Guest, Room, Stay, StayPlan
from app.service import posting_service
from app.service.folio_service import folio_out
from app.service.stay_service import CENT, get_stay, lock_folio, stay_out

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def catch_up(db, stays, now):
    """Post due room charges for these stays. Folios are locked in id order (no deadlocks)."""
    if not stays:
        return
    by_stay = {s.id: s for s in stays}
    folios = db.scalars(
        select(Folio)
        .where(Folio.stay_id.in_(by_stay), Folio.status == "open")
        .order_by(Folio.id)
        .with_for_update()
    ).all()
    for folio in folios:
        try:
            posting_service.post_due_room_charges(db, folio, by_stay[folio.stay_id], now)
        except posting_service.TooManyPeriods:
            # One stay with a wrong check-in time must not break the whole grid or list.
            # Nothing was inserted for it; opening that stay shows the error.
            continue


def balances(db, folio_ids):
    """folio_id -> balance (debits - credits), in one grouped query."""
    result = {folio_id: Decimal("0.00") for folio_id in folio_ids}
    if not folio_ids:
        return result
    signed = case((FolioTransaction.direction == "debit", FolioTransaction.amount),
                  else_=-FolioTransaction.amount)
    rows = db.execute(
        select(FolioTransaction.folio_id, func.sum(signed))
        .where(FolioTransaction.folio_id.in_(folio_ids))
        .group_by(FolioTransaction.folio_id)
    )
    for folio_id, total in rows:
        result[folio_id] = Decimal(total).quantize(CENT)
    return result


def _clamp(limit, offset):
    return max(1, min(limit or DEFAULT_LIMIT, MAX_LIMIT)), max(0, offset or 0)


def _stay_rows(db, tenant_id, conditions, order_by, limit, offset):
    return db.execute(
        select(Stay, Room.room_number, Guest, StayPlan.name, Folio)
        .join(Room, Room.id == Stay.room_id)
        .join(Guest, Guest.id == Stay.guest_id)
        .join(StayPlan, StayPlan.id == Stay.stay_plan_id)
        .join(Folio, Folio.stay_id == Stay.id)
        .where(Stay.tenant_id == tenant_id, *conditions)
        .order_by(*order_by)
        .limit(limit)
        .offset(offset)
    ).all()


def _summaries(db, rows):
    totals = balances(db, [folio.id for *_, folio in rows])
    out = []
    for stay, room_number, guest, plan_name, folio in rows:
        out.append({
            "id": stay.id,
            "status": stay.status,
            "room_id": stay.room_id,
            "room_number": room_number,
            "guest_id": guest.id,
            "guest_name": guest.full_name,
            "guest_phone": guest.phone,
            "stay_plan_name": plan_name,
            "occupancy": stay.occupancy,
            "actual_check_in_at": stay.actual_check_in_at,
            "expected_checkout_at": stay.expected_checkout_at,
            "actual_checkout_at": stay.actual_checkout_at,
            "agreed_price": stay.agreed_price,
            "folio_id": folio.id,
            "folio_status": folio.status,
            "balance": totals[folio.id],
            "forced_checkout_reason": folio.forced_checkout_reason,
        })
    return out


def list_stays(db, principal, *, status, limit, offset, now):
    """Active stays (by room number) or checked-out stays (latest first). Active ones post first."""
    limit, offset = _clamp(limit, offset)
    if status == "active":
        order_by = (Room.room_number,)
    else:
        order_by = (Stay.actual_checkout_at.desc(), Stay.id.desc())
    rows = _stay_rows(db, principal.tenant_id, [Stay.status == status], order_by, limit, offset)
    if status == "active":
        catch_up(db, [row[0] for row in rows], now)
        db.commit()
    return _summaries(db, rows)


def pending_balances(db, principal, *, limit, offset, now):
    """Checked-out stays whose folio is still open: the guest left owing money (DL-P08)."""
    limit, offset = _clamp(limit, offset)
    rows = _stay_rows(
        db, principal.tenant_id,
        [Stay.status == "checked_out", Folio.status == "open"],
        (Stay.actual_checkout_at.desc(), Stay.id.desc()), limit, offset,
    )
    catch_up(db, [row[0] for row in rows], now)
    db.commit()
    return _summaries(db, rows)


def stay_detail(db, principal, stay_id, *, now):
    """The stay with its full folio. Opening it posts due room charges (DL-R21)."""
    stay = get_stay(db, principal.tenant_id, stay_id)
    folio = lock_folio(db, stay)
    posting_service.post_due_room_charges(db, folio, stay, now)
    db.commit()
    return {**stay_out(db, stay), "folio": folio_out(db, folio)}
