from pydantic import BaseModel

class LoginRequest(BaseModel):
    email: str
    password: str

class SignupRequest(BaseModel):
    tenant_name: str
    admin_phone: str
    admin_email: str
    admin_password: str
    address: str | None = None
    name: str

class SignupResponse(BaseModel):
    tenant_id: int
    tenant_name: str
    user_id: int
    name: str
    email: str
    address: str | None

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str

class RegisterResponse(BaseModel):
    tenant_id: int
    name: str
    id: int
    email: str
    role: str

    model_config = {"from_attributes": True}

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}