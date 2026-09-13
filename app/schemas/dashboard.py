from pydantic import BaseModel
from datetime import datetime

class RoomCard(BaseModel):
    room_id: int
    room_number: str
    status: str
    guest_name: str | None = None
    check_in_at: datetime | None = None
    expected_checkout_at: datetime | None = None

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