from sqlalchemy.orm import Session, joinedload
from app.models.room import Room, RoomType
from app.models.stay import Stay

def get_room(db: Session, tenant_id: int, room_id: int):
    return db.query(Room).filter(Room.tenant_id == tenant_id, Room.id == room_id).first()



def get_room_for_dashboard(db: Session, tenant_id: int) -> list[Room]:
    return db.query(Room).filter(
        Room.tenant_id == tenant_id
    ).options(
        joinedload(Room.room_type).joinedload(RoomType.prices),
        joinedload(Room.stays.and_(Stay.status == "active")).joinedload(Stay.guest)).all()


def get_room_with_active_stay(db: Session, tenant_id: int, room_id: int) -> Room | None:
    return (
        db.query(Room)
        .filter(Room.id == room_id, Room.tenant_id == tenant_id)
        .options(
            joinedload(Room.room_type),
            joinedload(Room.stays.and_(Stay.status == "active")).joinedload(Stay.guest),
        )
        .first()
    )