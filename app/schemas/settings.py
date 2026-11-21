from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SettingsOut(BaseModel):
    timezone: str
    currency: str
    billing_mode: str  # only rolling_24h in the beta
    max_backdate_minutes: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SettingsUpdate(BaseModel):
    """Only the fields sent are changed. billing_mode is fixed in the beta (DL-R02)."""
    timezone: str | None = Field(default=None, min_length=1, max_length=64)  # IANA, e.g. Asia/Kolkata
    currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")      # ISO 4217, e.g. INR
    max_backdate_minutes: int | None = Field(default=None, ge=0, le=1440)
