from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class StayCard(BaseModel):
    """The guest in an occupied room."""
    stay_id: int
    guest_name: str
    guest_phone: str
    stay_plan_name: str
    actual_check_in_at: datetime
    expected_checkout_at: datetime | None
    agreed_price: Decimal
    balance: Decimal  # > 0 the guest owes; < 0 the guest is in credit
    next_charge_at: datetime  # when the next period posts (stay's own period + grace)


class RoomCard(BaseModel):
    room_id: int
    room_number: str
    room_type_name: str
    status: str  # available | cleaning | maintenance | occupied
    stay: StayCard | None


class DashboardSummary(BaseModel):
    total_rooms: int
    available: int
    occupied: int
    cleaning: int
    maintenance: int
    pending_balances_count: int   # checked-out guests who still owe
    pending_balances_total: Decimal


class DashboardOut(BaseModel):
    summary: DashboardSummary
    rooms: list[RoomCard]
