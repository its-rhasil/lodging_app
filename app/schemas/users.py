from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Tenant users can only create these. tenant_admin is created by the platform (DL-R05).
AssignableRole = Literal["manager", "receptionist"]


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(max_length=128)  # length rules: security.validate_new_password
    role_code: AssignableRole


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role_code: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OverrideIn(BaseModel):
    permission_code: str = Field(min_length=1, max_length=64)
    effect: Literal["grant", "deny"]
    reason: str | None = Field(default=None, max_length=500)


class OverridesUpdate(BaseModel):
    """The full list: overrides not in it are removed."""
    overrides: list[OverrideIn] = Field(max_length=50)


class OverrideOut(BaseModel):
    permission_code: str
    effect: str
    reason: str | None
    created_by_user_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserDetail(UserOut):
    overrides: list[OverrideOut]
    permissions: list[str]  # effective set
