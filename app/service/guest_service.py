from sqlalchemy.orm import Session

from app.models.guest import Guest


def create_guest(db: Session, tenant_id: int, full_name: str, phone: str, email: str | None, address: str | None):
    guest = Guest(
        tenant_id = tenant_id,
        full_name = full_name,
        phone = phone,
        email = email,
        address = address
    )
    db.add(guest)
    db.flush()
    db.refresh(guest)
    return guest

def get_guest(db: Session, tenant_id: int, guest_id: int):
    return db.query(Guest).filter(Guest.id == guest_id, Guest.tenant_id == tenant_id).first()