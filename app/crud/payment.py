from decimal import Decimal
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.payment import Payment


def create_payment(db: Session, tenant_id: int, stay_id: int, amount: Decimal, method: str) -> Payment:
    payment = Payment(tenant_id=tenant_id, stay_id=stay_id, amount=amount, method=method)
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment

def get_total_paid(db: Session, tenant_id: int, stay_id: int) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.tenant_id == tenant_id, Payment.stay_id == stay_id)
        .scalar()
    )
    return Decimal(total)