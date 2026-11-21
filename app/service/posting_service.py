"""Room-charge posting engine (architecture.md §8.2, DL-R08, P4-4).

When charges post (owner decision, 2026-11-16):
- period 1 at check-in;
- later periods only when someone works with the folio after the period's deadline + grace:
  opening it, or any folio action (checkout, payment, charge, waiver, refund, reversal,
  room change). Each of those calls post_due_room_charges() first, inside its own request.
There is no background job. Nothing posts while nobody touches the folio.

Price (owner decision, 2026-11-17): each period is charged at the stay's agreed_price at
posting time, i.e. the price of the room the guest is in when the period falls due.
This holds because a room change posts everything due before it changes the price.

Safety:
- the caller locks the folio (FOR UPDATE) first, so two requests can't post at once;
- posting_key 'room:<stay_plan_id>:<n>' is unique per folio, so a period can never post twice;
- period_start_at records when the period began, separately from created_at.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.models import Folio, FolioTransaction, Stay, StayPlan

# Safety limit (owner, 2026-11-17): a wrong check-in time (e.g. year 0026) must not post
# hundreds of thousands of charges. 400 is over a year of daily periods, or 16 days of hourly
# ones nobody opened; anything more is almost certainly a data error.
MAX_PERIODS_PER_CATCH_UP = 400


class TooManyPeriods(Conflict):
    code = "too_many_periods"


def periods_due(check_in: datetime, horizon: datetime, period_hours: int, grace_minutes: int) -> int:
    """How many periods are due at `horizon`: 1 + floor((elapsed - grace) / period), never below 1.

    Example (24h, grace 30m, check-in Mon 08:00): Tue 08:29 -> 1, Tue 08:30 -> 2.
    """
    past_grace = horizon - check_in - timedelta(minutes=grace_minutes)
    return 1 + max(0, past_grace // timedelta(hours=period_hours))


def next_charge_at(check_in: datetime, now: datetime, period_hours: int, grace_minutes: int) -> datetime:
    """When the next period will post: check-in + (periods due now) x period + grace.

    Example (24h, grace 30m, check-in 18 Nov 00:24): 1 period due -> next charge 19 Nov 00:54.
    Read-only; used by the room grid.
    """
    due = periods_due(check_in, now, period_hours, grace_minutes)
    return check_in + due * timedelta(hours=period_hours) + timedelta(minutes=grace_minutes)


def period_start(check_in: datetime, period_no: int, period_hours: int) -> datetime:
    """When period n began: check-in + (n - 1) x period."""
    return check_in + (period_no - 1) * timedelta(hours=period_hours)


def room_posting_key(stay_plan_id: int, period_no: int) -> str:
    """'room:<plan>:<n>'. The plan id keeps a converted stay's daily periods from clashing."""
    return f"room:{stay_plan_id}:{period_no}"


def post_due_room_charges(db: Session, folio: Folio, stay: Stay, now: datetime) -> list[FolioTransaction]:
    """Post every room-charge period that is due and not posted yet. Caller holds the folio lock.

    The horizon is `now` for an active stay and the checkout time for a checked-out stay.
    Only flushes: the caller's single commit saves the charges together with its own change.
    """
    if stay.status == "cancelled":
        return []
    horizon = stay.actual_checkout_at if stay.status == "checked_out" else now
    n_due = periods_due(stay.actual_check_in_at, horizon, stay.period_hours, stay.grace_minutes)

    last_posted = db.scalar(
        select(func.max(FolioTransaction.period_no)).where(
            FolioTransaction.folio_id == folio.id,
            FolioTransaction.txn_type == "room_charge",
            FolioTransaction.posting_key.startswith(f"room:{stay.stay_plan_id}:"),
        )
    ) or 0
    if last_posted >= n_due:
        return []
    if n_due - last_posted > MAX_PERIODS_PER_CATCH_UP:
        raise TooManyPeriods(
            f"The check-in time of this stay looks wrong: {n_due - last_posted} periods would be "
            "charged at once. Nothing was posted. Ask support to correct the check-in time.",
            details={"stay_id": stay.id, "periods": n_due - last_posted},
        )

    plan_name = db.scalar(select(StayPlan.name).where(StayPlan.tenant_id == stay.tenant_id,
                                                      StayPlan.id == stay.stay_plan_id))
    posted = []
    for n in range(last_posted + 1, n_due + 1):
        txn = FolioTransaction(
            tenant_id=folio.tenant_id, folio_id=folio.id, txn_type="room_charge", direction="debit",
            amount=stay.agreed_price, description=f"{plan_name} {n}",
            posting_key=room_posting_key(stay.stay_plan_id, n),
            period_no=n, period_start_at=period_start(stay.actual_check_in_at, n, stay.period_hours),
            created_by_user_id=None,  # NULL = system (the posting engine)
        )
        db.add(txn)
        posted.append(txn)
    db.flush()
    return posted
