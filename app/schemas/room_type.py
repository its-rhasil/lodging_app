from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RateIn(BaseModel):
    """Price per period of a stay plan, for one occupancy."""
    stay_plan_id: int
    occupancy: int = Field(ge=1)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class RoomTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    capacity: int = Field(ge=1, le=50)
    rates: list[RateIn] = Field(min_length=1, max_length=500)


class RoomTypeUpdate(BaseModel):
    """Only the fields sent are changed. `rates`, when sent, replaces the full rate set."""
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    capacity: int | None = Field(default=None, ge=1, le=50)
    is_active: bool | None = None
    rates: list[RateIn] | None = Field(default=None, min_length=1, max_length=500)


class RateOut(BaseModel):
    stay_plan_id: int
    occupancy: int
    price: Decimal

    model_config = ConfigDict(from_attributes=True)


class RoomTypeOut(BaseModel):
    id: int
    name: str
    description: str | None
    capacity: int
    is_active: bool
    created_at: datetime
    rates: list[RateOut]

    model_config = ConfigDict(from_attributes=True)
