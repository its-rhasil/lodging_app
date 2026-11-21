"""Room grid (DL-E04, DL-R21): every active room with its effective status, the guest in it
and their balance. Loading it posts due room charges for the guests shown (owner, 2026-11-17).
"""
from decimal import Decimal

from sqlalchemy import select

from app.models import Folio, Guest, Room, RoomType, Stay, StayPlan
from app.service.posting_service import next_charge_at
from app.service.stay_read_service import balances, catch_up


def build_dashboard(db, principal, *, now):
    tenant_id = principal.tenant_id

    rooms = db.execute(
        select(Room, RoomType.name)
        .join(RoomType, RoomType.id == Room.room_type_id)
        .where(Room.tenant_id == tenant_id, Room.is_active.is_(True))
        .order_by(Room.room_number)
    ).all()

    active = db.execute(
        select(Stay, Guest, StayPlan.name, Folio)
        .join(Guest, Guest.id == Stay.guest_id)
        .join(StayPlan, StayPlan.id == Stay.stay_plan_id)
        .join(Folio, Folio.stay_id == Stay.id)
        .where(Stay.tenant_id == tenant_id, Stay.status == "active")
    ).all()

    pending_folio_ids = list(db.scalars(
        select(Folio.id)
        .join(Stay, Stay.id == Folio.stay_id)
        .where(Stay.tenant_id == tenant_id, Stay.status == "checked_out", Folio.status == "open")
    ))

    # Post due charges for the guests on the grid, then read every balance in one query.
    catch_up(db, [stay for stay, *_ in active], now)
    db.commit()
    totals = balances(db, [folio.id for *_, folio in active] + pending_folio_ids)

    stay_by_room = {stay.room_id: (stay, guest, plan_name, folio) for stay, guest, plan_name, folio in active}
    counts = {"available": 0, "occupied": 0, "cleaning": 0, "maintenance": 0}
    cards = []
    for room, type_name in rooms:
        card_stay = None
        if room.id in stay_by_room:
            stay, guest, plan_name, folio = stay_by_room[room.id]
            status = "occupied"
            card_stay = {
                "stay_id": stay.id,
                "guest_name": guest.full_name,
                "guest_phone": guest.phone,
                "stay_plan_name": plan_name,
                "actual_check_in_at": stay.actual_check_in_at,
                "expected_checkout_at": stay.expected_checkout_at,
                "agreed_price": stay.agreed_price,
                "balance": totals[folio.id],
                # The stay's own period/grace copy (not the plan's current settings).
                "next_charge_at": next_charge_at(stay.actual_check_in_at, now, stay.period_hours,
                                                 stay.grace_minutes),
            }
        else:
            status = room.operational_status
        counts[status] += 1
        cards.append({
            "room_id": room.id,
            "room_number": room.room_number,
            "room_type_name": type_name,
            "status": status,
            "stay": card_stay,
        })

    return {
        "summary": {
            "total_rooms": len(rooms),
            **counts,
            "pending_balances_count": len(pending_folio_ids),
            "pending_balances_total": sum((totals[f] for f in pending_folio_ids), Decimal("0.00")),
        },
        "rooms": cards,
    }
