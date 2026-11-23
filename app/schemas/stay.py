from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.schemas.folio import FolioOut
from app.schemas.guest import GuestIn, GuestOut


class CheckInRequest(BaseModel):
    room_id: int
    stay_plan_id: int
    occupancy: int = Field(ge=1)
    # Exactly one of: guest_id (reuse a guest found by phone) or guest (create a new one).
    guest_id: int | None = None
    guest: GuestIn | None = None
    # Left out: the listed (rate-table) price is used. Lower: a discount (stay.override_rate).
    agreed_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    rate_reason: str | None = Field(default=None, max_length=500)  # optional (owner, 2026-11-16)
    # Left out: now. Must carry a timezone (D-08). Earlier than the tenant's window: stay.backdate + reason.
    check_in_at: AwareDatetime | None = None
    backdate_reason: str | None = Field(default=None, max_length=500)
    expected_checkout_at: AwareDatetime | None = None  # informational only

    @model_validator(mode="after")
    def one_guest_source(self):
        if (self.guest_id is None) == (self.guest is None):
            raise ValueError("Send either guest_id or guest, not both.")
        return self


class CheckoutIn(BaseModel):
    # Only for a forced checkout: the guest leaves owing money (folio.close_with_balance, DL-P08).
    force_reason: str | None = Field(default=None, max_length=500)
    # When the guest actually left (owner, 2026-11-23). Left out: now. Must carry a timezone.
    checkout_at: AwareDatetime | None = None
    backdate_reason: str | None = Field(default=None, max_length=500)


class ExtendIn(BaseModel):
    expected_checkout_at: AwareDatetime  # informational: posting continues while the stay is active


class ChangeRoomIn(BaseModel):
    new_room_id: int
    # DL-R23: the price entered for the new room, else the new room's listed price.
    agreed_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    rate_reason: str | None = Field(default=None, max_length=500)  # optional, like check-in
    reason: str | None = Field(default=None, max_length=500)       # why the guest moved, e.g. "AC broken"


class ConvertIn(BaseModel):
    # DL-R23: default is the daily plan's listed price for this occupancy; lower is a discount.
    agreed_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    rate_reason: str | None = Field(default=None, max_length=500)


class CancelIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)  # e.g. "wrong room", "guest left"


class CorrectPriceIn(BaseModel):
    """Fix a wrongly entered price (manager). Charges already posted at the old price are re-posted."""
    agreed_price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)


class OfferOut(BaseModel):
    """A plan the room offers at an occupancy, with its listed price per period."""
    stay_plan_id: int
    name: str
    period_hours: int
    grace_minutes: int
    is_daily: bool
    listed_price: Decimal


class FolioSummary(BaseModel):
    id: int
    status: str
    balance: Decimal  # > 0 the guest owes; < 0 the guest is in credit


class StayOut(BaseModel):
    id: int
    status: str
    room_id: int
    room_number: str
    guest: GuestOut
    stay_plan_id: int
    stay_plan_name: str
    occupancy: int
    period_hours: int     # copied from the plan at check-in
    grace_minutes: int    # copied from the plan at check-in
    actual_check_in_at: datetime
    expected_checkout_at: datetime | None
    actual_checkout_at: datetime | None
    listed_price: Decimal
    agreed_price: Decimal
    discount_percent: Decimal  # (listed - agreed) / listed x 100, 2 decimals
    folio: FolioSummary


class StayDetailOut(StayOut):
    """GET /stays/{id}: the stay with its full folio (opening it posts due charges)."""
    folio: FolioOut


class StaySummary(BaseModel):
    """One row of the active-stays and pending-balances lists."""
    id: int
    status: str
    room_id: int
    room_number: str
    guest_id: int
    guest_name: str
    guest_phone: str
    stay_plan_name: str
    occupancy: int
    actual_check_in_at: datetime
    expected_checkout_at: datetime | None
    actual_checkout_at: datetime | None
    agreed_price: Decimal
    folio_id: int
    folio_status: str
    balance: Decimal
    forced_checkout_reason: str | None
