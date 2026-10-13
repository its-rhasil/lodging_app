from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone

from app.service.status_service import get_effective_status
from app.crud.room import get_room_for_dashboard
from app.schemas.dashboard import RoomCard, DashboardResponse, DashboardSummary
from app.models.stay import Stay

def get_today_counts(db: Session, tenant_id: int) -> dict:
    today = datetime.now(timezone.utc).date()
    checkins = (
        db.query(func.count(Stay.id))
        .filter(Stay.tenant_id == tenant_id, func.date(Stay.actual_check_in_at) == today)
        .scalar()
    )
    checkouts = (
        db.query(func.count(Stay.id))
        .filter(Stay.tenant_id == tenant_id, func.date(Stay.actual_checkout_at) == today)
        .scalar()
    )
    return {"checkins_today": checkins, "checkouts_today": checkouts}


def build_dashboard(db: Session, tenant_id: int)-> DashboardResponse:
    rooms = get_room_for_dashboard(db=db, tenant_id=tenant_id)

    cards = []
    counts = {"available":0, "maintenance": 0, "cleaning": 0, "occupied": 0, "reserved": 0}

    for room in rooms:
        status = get_effective_status(room)
        counts[status] += 1

        active_stay = room.stays[0] if room.stays else None
        nightly_rate = active_stay.agreed_price if active_stay else None
        min_price = max_price = None

        if status == "available" and room.room_type.prices:
            prices = [p.price for p in room.room_type.prices]
            min_price, max_price = min(prices), max(prices)

        cards.append(
            RoomCard(
            room_id=room.id,
            room_number=room.room_number,
            room_type_name=room.room_type.name,
            status=status,
            guest_name=active_stay.guest.full_name if active_stay else None,
            nightly_rate=active_stay.agreed_price if active_stay else None,
            min_price = min_price,
            max_price = max_price,
            )
        )

    summary = DashboardSummary(
        total_rooms=len(rooms),
        available=counts["available"],
        occupied=counts["occupied"],
        cleaning=counts["cleaning"],
        maintenance=counts["maintenance"],
        reserved=counts["reserved"]
    )
    return DashboardResponse(summary=summary, rooms=cards)

