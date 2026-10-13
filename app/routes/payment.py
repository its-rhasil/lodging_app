from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.schemas.payment import PaymentCreate, BillingSummary
from app.service.payment_service import record_payment

router = APIRouter(prefix="/stays", tags=["payments"], dependencies=[Depends(get_current_user)])


@router.post("/{stay_id}/payments", response_model=BillingSummary, status_code=201)
def record_payment_endpoint(
    stay_id: int,
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return record_payment(
        db,
        tenant_id=current_user.tenant_id,
        stay_id=stay_id,
        amount=payload.amount,
        method=payload.method,
    )