from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    # No minimum here: length rules apply when a password is set, not when one is checked.
    password: str = Field(min_length=1, max_length=128)


class MeResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    email: str
    role_code: str
    permissions: list[str]  # effective set; the frontend uses it to show or hide actions

    model_config = ConfigDict(from_attributes=True)
