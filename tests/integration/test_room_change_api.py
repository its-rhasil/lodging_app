"""Room change in place (M1 Day 3, task 2; DL-R13, DL-R21, DL-R23).

The fake clock starts at Mon 2026-11-16 08:00 UTC. Check-in: full day, room 101 at 1000/day.
"""
import uuid

import pytest

from app.models import AuditEvent, Room, StayRoomMove
from tests.factories import (
    daily_plan, log_in, make_plan, make_room, make_room_type, make_stay, make_tenant, make_user,
)


@pytest.fixture
def tenant(db):
    return make_tenant(db)


@pytest.fixture
def receptionist(db, tenant):
    return make_user(db, tenant, role_code="receptionist")


@pytest.fixture
def rooms(db, tenant):
    """101 at 1000 (cap 2), 201 at 1500 (cap 2), 105 at 800 (cap 2), 301 single at 600 (cap 1)."""
    def room(number, price, capacity=2):
        return make_room(db, tenant, number=number,
                         room_type=make_room_type(db, tenant, capacity=capacity, daily_price=price))
    return {"101": room("101", "1000.00"), "201": room("201", "1500.00"),
            "105": room("105", "800.00"), "301": room("301", "600.00", capacity=1)}


def login(db, client, user):
    log_in(client, db, user)
    db.commit()


def check_in(db, client, tenant, room, occupancy=2, plan=None):
    res = client.post("/stays", json={
        "room_id": room.id, "stay_plan_id": (plan or daily_plan(db, tenant)).id, "occupancy": occupancy,
        "guest": {"full_name": "Ravi Kumar", "phone": "9876543210"},
    })
    assert res.status_code == 201, res.json()
    return res.json()["id"]


def move(client, stay_id, room, **extra):
    return client.post(f"/stays/{stay_id}/change-room", json={"new_room_id": room.id, **extra})


def room_charge_amounts(client, stay_id):
    folio = client.get(f"/stays/{stay_id}/folio").json()
    return [t["amount"] for t in folio["transactions"] if t["txn_type"] == "room_charge"]


# --- prices ------------------------------------------------------------------

def test_dearer_room_charges_due_days_at_the_old_price(db, client, tenant, rooms, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, rooms["101"])
    fake_clock.advance(hours=31)                           # Tue 15:00: day 2 already due

    res = move(client, stay_id, rooms["201"], reason="AC broken")
    assert res.status_code == 200
    body = res.json()
    assert (body["room_number"], body["listed_price"], body["agreed_price"]) == ("201", "1500.00", "1500.00")

    fake_clock.advance(hours=17, minutes=31)               # Wed 08:31: day 3 due
    assert room_charge_amounts(client, stay_id) == ["1000.00", "1000.00", "1500.00"]


def test_move_inside_the_grace_uses_the_new_price(db, client, tenant, rooms, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, rooms["101"])
    fake_clock.advance(hours=24, minutes=15)               # Tue 08:15: day 2 not due until 08:30
    move(client, stay_id, rooms["201"])
    fake_clock.advance(minutes=20)
    assert room_charge_amounts(client, stay_id) == ["1000.00", "1500.00"]


def test_entered_discount_for_the_new_room(db, client, tenant, rooms, receptionist):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, rooms["101"])
    body = move(client, stay_id, rooms["105"], agreed_price="700").json()
    assert (body["listed_price"], body["agreed_price"], body["discount_percent"]) == ("800.00", "700.00", "12.50")


def test_price_above_the_new_listed_price_is_rejected(db, client, tenant, rooms, receptionist):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, rooms["101"])
    res = move(client, stay_id, rooms["105"], agreed_price="900")
    assert res.status_code == 422
    assert res.json()["code"] == "price_above_listed"


# --- bookkeeping ---------------------------------------------------------------

def test_move_is_recorded_and_old_room_goes_to_cleaning(db, client, tenant, rooms, receptionist):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, rooms["101"])
    move(client, stay_id, rooms["201"], reason="AC broken")

    [record] = db.query(StayRoomMove).filter_by(stay_id=stay_id).all()
    assert (record.from_room_id, record.to_room_id, str(record.rate_before), str(record.rate_after)) == (
        rooms["101"].id, rooms["201"].id, "1000.00", "1500.00")
    assert record.moved_by_user_id == receptionist.id
    assert db.get(Room, rooms["101"].id).operational_status == "cleaning"
    assert client.get(f"/rooms/{rooms['201'].id}").json()["status"] == "occupied"
    [event] = db.query(AuditEvent).filter_by(action="stay.room_changed").all()
    assert event.reason == "AC broken"


# --- rejections ----------------------------------------------------------------

def test_new_room_must_be_free(db, client, tenant, rooms, receptionist):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, rooms["101"])
    make_stay(db, tenant, receptionist, room=rooms["201"])
    rooms["105"].operational_status = "maintenance"
    db.commit()
    assert move(client, stay_id, rooms["201"]).json()["code"] == "room_occupied"
    assert move(client, stay_id, rooms["105"]).json()["code"] == "room_not_available"


def test_new_room_must_fit_the_guests(db, client, tenant, rooms, receptionist):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, rooms["101"], occupancy=2)
    assert move(client, stay_id, rooms["301"]).json()["code"] == "occupancy_exceeds_capacity"


def test_new_room_must_offer_the_stay_plan(db, client, tenant, rooms, receptionist):
    freshup = make_plan(db, tenant, name="Fresh-up")
    with_freshup = make_room(db, tenant, number="401", room_type=make_room_type(
        db, tenant, capacity=2, extra_rates={(freshup.id, 2): "500.00"}))
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, with_freshup, plan=freshup)
    assert move(client, stay_id, rooms["201"]).json()["code"] == "plan_not_offered"


def test_same_room_and_checked_out_stay_are_rejected(db, client, tenant, rooms, receptionist):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, rooms["101"])
    assert move(client, stay_id, rooms["101"]).json()["code"] == "same_room"

    client.post(f"/stays/{stay_id}/folio/payments",
                json={"amount": "1000", "method": "cash", "idempotency_key": str(uuid.uuid4())})
    client.post(f"/stays/{stay_id}/checkout")
    assert move(client, stay_id, rooms["201"]).json()["code"] == "stay_not_active"


def test_another_tenants_room_is_not_found(db, client, tenant, rooms, receptionist):
    foreign = make_room(db, make_tenant(db))
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, rooms["101"])
    assert move(client, stay_id, foreign).status_code == 404
