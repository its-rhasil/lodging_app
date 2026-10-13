from app.models.room import Room

def get_effective_status(room: Room):
    if any(stay.status == "active" for stay in room.stays):
        return "occupied"

    return room.operational_status

def set_operational_status(room: Room, status: str):
    room.operational_status = status
    return room
