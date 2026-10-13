from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal


class RoomCard(BaseModel):
    room_id: int
    room_number: str
    room_type_name: str
    status: str
    guest_name: str | None = None
    nightly_rate: Decimal | None = None       # occupied rooms: the agreed rate
    min_price: Decimal | None = None          # available rooms: cheapest occupancy tier
    max_price: Decimal | None = None          # available rooms: priciest occupancy tier

    model_config = {"from_attributes": True}

class DashboardSummary(BaseModel):
    total_rooms: int
    available: int
    occupied: int
    cleaning: int
    maintenance: int
    reserved: int  # placeholder, always 0 for now


class DashboardResponse(BaseModel):
    summary: DashboardSummary
    rooms: list[RoomCard]