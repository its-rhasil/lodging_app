from sqlalchemy.orm import Session, joinedload
from app.models.stay import Stay

def get_stay(db: Session, tenant_id: int, stay_id: int):
    return db.query(Stay).filter(Stay.id == stay_id, Stay.tenant_id == tenant_id).first()

# app/crud/stay.py
def get_stay_history(db: Session, tenant_id: int, room_id: int) -> list[Stay]:
    return (
        db.query(Stay)
        .filter(Stay.tenant_id == tenant_id, Stay.room_id == room_id, Stay.status == "checked_out")
        .options(joinedload(Stay.guest))
        .order_by(Stay.actual_check_in_at.desc())
        .all()
    )