from decimal import Decimal
from pydantic import BaseModel


class PaymentCreate(BaseModel):
    amount: Decimal
    method: str


class BillingSummary(BaseModel):
    occupancy: int
    nightly_rate: Decimal
    nights: int
    total: Decimal
    paid: Decimal
    balance: Decimal
    status: str