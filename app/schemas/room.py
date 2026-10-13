from pydantic import BaseModel
from datetime import datetime

from app.schemas.payment import BillingSummary


class RoomCreate(BaseModel):
    room_type_id: int
    room_number: int

class RoomOut(BaseModel):
    id: int
    room_number: str
    room_type_id: int
    operational_status: str

    model_config = {"from_attributes": True}

class RoomResponse(BaseModel):
    id: int
    room_number: str
    room_type_id: int
    operational_status: str

    model_config = {"from_attributes": True}

# app/schemas/room.py
class GuestOut(BaseModel):
    full_name: str
    phone: str
    email: str | None
    address: str | None

    model_config = {"from_attributes": True}


class RoomDetail(BaseModel):
    room_id: int
    stay_id: int | None
    room_number: str
    room_type_name: str
    status: str
    guest: GuestOut | None = None
    actual_check_in_at: datetime | None = None
    expected_checkout_at: datetime | None = None
    billing: BillingSummary | None = None



class RoomStatusUpdate(BaseModel):
    operational_status: str