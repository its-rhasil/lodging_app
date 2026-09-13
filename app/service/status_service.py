from app.models.room import Room

def get_effective_status(room: Room):
    if room.stays:
        return "occupied"

    return room.operational_status