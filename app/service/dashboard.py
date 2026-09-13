from sqlalchemy.orm import Session

from app.service.status_service import get_effective_status
from app.service.room_service import get_room_for_dashboard
from app.schemas.dashboard import RoomCard, DashboardResponse, DashboardSummary

def build_dashboard(db: Session, tenant_id: int)-> DashboardResponse:
    rooms = get_room_for_dashboard(db=db, tenant_id=tenant_id)

    cards = []
    counts = {"available":0, "maintenance": 0, "cleaning": 0, "occupied": 0, "reserved": 0}

    for room in rooms:
        status = get_effective_status(room)
        counts[status] += 1

        active_stay = room.stays[0] if room.stays else None
        cards.append(
            RoomCard(
                room_id= room.id,
                room_number= room.room_number,
                status = status,
                guest_name = active_stay.guest.full_name if active_stay else None,
                check_in_at= active_stay.actual_check_in_at if active_stay else None,
                expected_checkout_at= active_stay.expected_checkout_at if active_stay else None
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
    return DashboardResponse(summary, cards)