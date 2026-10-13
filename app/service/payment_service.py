import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud.stay import get_stay
from app.crud.payment import create_payment, get_total_paid

CHECKOUT_GRACE = timedelta(hours=2)  # becomes a per-tenant setting later


def calculate_nights(check_in_at: datetime, billable_until: datetime, grace: timedelta = CHECKOUT_GRACE) -> int:
    elapsed = billable_until - check_in_at
    return max(1, math.ceil((elapsed - grace) / timedelta(hours=24)))


def get_billing_summary(db: Session, tenant_id: int, stay) -> dict:
    now = datetime.now(timezone.utc)

    if stay.actual_checkout_at is not None:
        billable_until = stay.actual_checkout_at
    else:
        billable_until = now

    nights = calculate_nights(stay.actual_check_in_at, billable_until)
    total = stay.agreed_price * nights
    paid = get_total_paid(db, tenant_id, stay.id)
    balance = total - paid

    if paid <= 0:
        status = "unpaid"
    elif balance > 0:
        status = "partial"
    else:
        status = "paid"

    return {
        "occupancy": stay.occupancy, 
        "nightly_rate": stay.agreed_price,
        "nights": nights,
        "total": total,
        "paid": paid,
        "balance": balance,
        "status": status,
    }

def record_payment(db: Session, tenant_id: int, stay_id: int, amount: Decimal, method: str):
    if amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be greater than zero")

    stay = get_stay(db, tenant_id, stay_id)
    if stay is None:
        raise HTTPException(status_code=404, detail="Stay not found")

    create_payment(db, tenant_id, stay_id, amount, method)
    return get_billing_summary(db, tenant_id, stay)