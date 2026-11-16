from pydantic import BaseModel


class PlatformMeResponse(BaseModel):
    id: int
    email: str
    name: str
