from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime
from app.schemas.payment import BillingSummary

class CheckInRequest(BaseModel):
    room_id: int
    guest_full_name: str
    guest_phone: str
    guest_email: str | None = None
    guest_address: str | None = None
    occupancy: int
    stay_hours: int
    agreed_price: Decimal
    actual_check_in_at: datetime | None = None 

class CheckInPreview(BaseModel):
    room_id: int
    room_type_name: str
    occupancy: int
    suggested_price: Decimal | None

class StayOut(BaseModel):
    id: int
    room_id: int
    guest_id: int
    status: str
    actual_check_in_at: datetime
    agreed_price: Decimal

    model_config = {"from_attributes": True}


class ExtendStayRequest(BaseModel):
    new_expected_checkout_at: datetime

class CheckoutResponse(BaseModel):
    stay: StayOut
    billing: BillingSummary


class StayHistoryEntry(BaseModel):
    guest_name: str
    actual_check_in_at: datetime
    actual_checkout_at: datetime | None
    agreed_price: Decimal
    billing: BillingSummary


class ChangeRoomPreview(BaseModel):
    mode: str
    suggested_price: Decimal | None
    old_balance_due_if_split: Decimal | None

class ConfirmRoomChangeRequest(BaseModel):
    new_room_id: int
    final_price: Decimal

class ChangeRoomResult(BaseModel):
    mode: str
    stay: StayOut | None = None
    old_stay: StayOut | None = None
    new_stay: StayOut | None = None