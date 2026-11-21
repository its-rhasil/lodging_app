from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# What staff can set. 'occupied' is never set by hand: it comes from an active stay (DL-E04).
OperationalStatus = Literal["available", "cleaning", "maintenance"]
EffectiveStatus = Literal["available", "cleaning", "maintenance", "occupied"]


class RoomCreate(BaseModel):
    room_type_id: int
    room_number: str = Field(min_length=1, max_length=20)  # string: '101', 'A-12' (D-27)


class RoomUpdate(BaseModel):
    """Only the fields sent are changed."""
    room_type_id: int | None = None
    room_number: str | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None


class RoomStatusUpdate(BaseModel):
    operational_status: OperationalStatus


class RoomOut(BaseModel):
    id: int
    room_number: str
    room_type_id: int
    room_type_name: str
    operational_status: OperationalStatus
    status: EffectiveStatus          # 'occupied' if there's an active stay, else operational_status
    active_stay_id: int | None
    is_active: bool
    created_at: datetime
