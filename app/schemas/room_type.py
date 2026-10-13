from pydantic import BaseModel
from decimal import Decimal

class RoomTypePriceIn(BaseModel):
    occupancy: int
    price: Decimal



class RoomtypeCreate(BaseModel):
    name: str
    description: str | None = None
    capacity: int
    prices: list[RoomTypePriceIn]

class RoomTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    capacity: int | None = None
    prices: list[RoomTypePriceIn] | None = None 

class RoomTypePriceOut(BaseModel):
    occupancy: int
    price: Decimal

    model_config = {"from_attributes": True}

class RoomTypeResponse(BaseModel):
    id: int
    name: str
    description: str | None
    capacity: int
    prices: list[RoomTypePriceOut]

    model_config = {"from_attributes": True}

class RoomTypeResponseWP(BaseModel):
    id: int
    name: str
    capacity: int
    model_config = {"from_attributes": True}
    