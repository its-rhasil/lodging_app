from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StayPlanCreate(BaseModel):
    """A non-daily plan (fresh-up, hourly, ...). The daily plan comes from create-tenant."""
    name: str = Field(min_length=1, max_length=50)
    period_hours: int = Field(ge=1, le=24)
    grace_minutes: int = Field(default=0, ge=0, le=240)
    sort_order: int = Field(default=0, ge=0, le=1000)


class StayPlanUpdate(BaseModel):
    """Only the fields sent are changed."""
    name: str | None = Field(default=None, min_length=1, max_length=50)
    period_hours: int | None = Field(default=None, ge=1, le=24)
    grace_minutes: int | None = Field(default=None, ge=0, le=240)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)


class StayPlanOut(BaseModel):
    id: int
    name: str
    period_hours: int
    grace_minutes: int
    is_daily: bool
    is_active: bool
    sort_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
