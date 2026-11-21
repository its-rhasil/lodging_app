from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class GuestIn(BaseModel):
    """A new guest, sent with a check-in when no existing guest_id is reused."""
    full_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=25)  # normalised by guest_service.normalize_phone
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=300)


class GuestOut(BaseModel):
    id: int
    full_name: str
    phone: str
    email: str | None
    address: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
