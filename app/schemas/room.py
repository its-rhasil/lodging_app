from pydantic import BaseModel

class RoomCreate(BaseModel):
    room_type_id: int
    room_number: int


class RoomResponse(BaseModel):
    id: int
    room_number: str
    room_type_id: int
    operational_status: str

    model_config = {"from_attributes": True}