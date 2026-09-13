from pydantic import BaseModel
from decimal import Decimal


class RoomtypeCreate(BaseModel):
    name: str
    description: str | None = None
    default_price: Decimal
    capacity: int

class RoomTypeResponse(BaseModel):
    id: int
    name: str
    description: str | None
    default_price: Decimal
    capacity: int
    model_config = {"from_attributes": True}
    