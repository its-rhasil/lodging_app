"""Checkout and extend (M1 Day 3, task 1). The fake clock starts at Mon 2026-11-16 08:00 UTC.

Each test checks in through the API: full day, 1000/day, grace 30 min, period 1 posted.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from app.models import AuditEvent, Folio, Room, Stay
from tests.factories import daily_plan, log_in, make_room, make_room_type, make_tenant, make_user


@pytest.fixture
def tenant(db):
    return make_tenant(db)


@pytest.fixture
def receptionist(db, tenant):
    return make_user(db, tenant, role_code="receptionist")


@pytest.fixture
def manager(db, tenant):
    return make_user(db, tenant, role_code="manager")


def login(db, client, user):
    log_in(client, db, user)
    db.commit()


def check_in(db, client, tenant):
    room = make_room(db, tenant, room_type=make_room_type(db, tenant, capacity=2, daily_price="1000.00"))
    db.commit()
    res = client.post("/stays", json={
        "room_id": room.id, "stay_plan_id": daily_plan(db, tenant).id, "occupancy": 1,
        "guest": {"full_name": "Ravi Kumar", "phone": "9876543210"},
    })
    assert res.status_code == 201
    return res.json()["id"], room.id


def pay(client, stay_id, amount):
    return client.post(f"/stays/{stay_id}/folio/payments",
                       json={"amount": amount, "method": "cash", "idempotency_key": str(uuid.uuid4())})


def folio_of(db, stay_id):
    return db.query(Folio).filter_by(stay_id=stay_id).one()


# --- settled checkout -----------------------------------------------------------

def test_settled_checkout_closes_folio_and_sends_room_to_cleaning(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, room_id = check_in(db, client, tenant)
    pay(client, stay_id, "1000")
    fake_clock.advance(hours=5)

    res = client.post(f"/stays/{stay_id}/checkout")
    assert res.status_code == 200
    body = res.json()
    assert (body["status"], body["folio"]["status"], body["folio"]["balance"]) == ("checked_out", "closed", "0.00")
    assert datetime.fromisoformat(body["actual_checkout_at"]) == fake_clock.now()
    folio = folio_of(db, stay_id)
    assert folio.closed_by_user_id == receptionist.id
    assert db.get(Room, room_id).operational_status == "cleaning"
    assert db.query(AuditEvent).filter_by(action="stay.checked_out").count() == 1


def test_checkout_posts_due_charges_first(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    pay(client, stay_id, "1000")
    fake_clock.advance(hours=24, minutes=40)           # Tue 08:40: day 2 is due

    res = client.post(f"/stays/{stay_id}/checkout")
    assert res.status_code == 403
    assert res.json()["code"] == "balance_outstanding"
    assert res.json()["details"]["balance"] == "1000.00"
    assert db.get(Stay, stay_id).status == "active"


def test_clock_stops_at_checkout(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    pay(client, stay_id, "1000")
    fake_clock.advance(hours=24, minutes=20)           # left inside the grace
    client.post(f"/stays/{stay_id}/checkout")
    fake_clock.advance(days=7)
    assert client.get(f"/stays/{stay_id}/folio").json()["balance"] == "0.00"


# --- forced checkout (balance owed) -------------------------------------------------

def test_forced_checkout_needs_a_reason(db, client, tenant, manager):
    login(db, client, manager)
    stay_id, _ = check_in(db, client, tenant)
    res = client.post(f"/stays/{stay_id}/checkout")
    assert res.status_code == 422
    assert res.json()["code"] == "reason_required"


def test_forced_checkout_keeps_the_folio_open_until_paid(db, client, tenant, manager):
    login(db, client, manager)
    stay_id, _ = check_in(db, client, tenant)

    res = client.post(f"/stays/{stay_id}/checkout", json={"force_reason": "Will pay by UPI tonight"})
    assert res.status_code == 200
    assert (res.json()["status"], res.json()["folio"]["status"]) == ("checked_out", "open")
    assert folio_of(db, stay_id).forced_checkout_reason == "Will pay by UPI tonight"
    [event] = db.query(AuditEvent).filter_by(action="stay.checked_out").all()
    assert event.reason == "Will pay by UPI tonight"

    settled = pay(client, stay_id, "1000").json()
    assert (settled["balance"], settled["status"]) == ("0.00", "closed")


# --- guest in credit ------------------------------------------------------------

def test_guest_in_credit_needs_a_refund_first(db, client, tenant, manager):
    login(db, client, manager)
    stay_id, _ = check_in(db, client, tenant)
    pay(client, stay_id, "1500")
    res = client.post(f"/stays/{stay_id}/checkout")
    assert res.status_code == 409
    assert res.json()["code"] == "refund_required"

    client.post(f"/stays/{stay_id}/folio/refunds", json={"amount": "500", "method": "cash", "reason": "Change"})
    assert client.post(f"/stays/{stay_id}/checkout").status_code == 200


# --- other ---------------------------------------------------------------------

def test_cannot_check_out_twice(db, client, tenant, receptionist):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    pay(client, stay_id, "1000")
    client.post(f"/stays/{stay_id}/checkout")
    res = client.post(f"/stays/{stay_id}/checkout")
    assert res.status_code == 409
    assert res.json()["code"] == "stay_not_active"


def test_another_tenants_stay_is_not_found(db, client, tenant, receptionist):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    login(db, client, make_user(db, make_tenant(db), role_code="manager"))
    assert client.post(f"/stays/{stay_id}/checkout").status_code == 404


# --- custom checkout time (owner, 2026-11-23) ------------------------------------------

def checkout_at(client, stay_id, when, **extra):
    return client.post(f"/stays/{stay_id}/checkout", json={"checkout_at": when.isoformat(), **extra})


def test_custom_checkout_time_is_saved_and_audited(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    pay(client, stay_id, "1000")
    fake_clock.advance(hours=5)
    left = fake_clock.now() - timedelta(hours=1)

    res = checkout_at(client, stay_id, left)
    assert res.status_code == 200
    assert datetime.fromisoformat(res.json()["actual_checkout_at"]) == left
    assert res.json()["folio"]["status"] == "closed"
    [event] = db.query(AuditEvent).filter_by(action="stay.checked_out").all()
    assert datetime.fromisoformat(event.changes["actual_checkout_at"][1]) == left
    assert event.reason is None


def test_charges_stop_at_the_custom_time(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    pay(client, stay_id, "1000")
    fake_clock.advance(hours=24, minutes=40)           # Tue 08:40: day 2 due since 08:30, not posted yet
    left = fake_clock.now() - timedelta(minutes=25)    # left Tue 08:15, inside the grace

    res = checkout_at(client, stay_id, left)
    assert res.status_code == 200
    assert (res.json()["folio"]["balance"], res.json()["folio"]["status"]) == ("0.00", "closed")
    fake_clock.advance(days=3)
    assert client.get(f"/stays/{stay_id}/folio").json()["balance"] == "0.00"


def test_charge_already_posted_after_the_time_blocks_until_reversed(db, client, tenant, receptionist,
                                                                    manager, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    pay(client, stay_id, "1000")
    fake_clock.advance(hours=24, minutes=40)
    client.get(f"/stays/{stay_id}")                    # opening the stay posts day 2
    left = fake_clock.now() - timedelta(minutes=25)

    res = checkout_at(client, stay_id, left)
    assert res.status_code == 409
    assert res.json()["code"] == "charges_after_checkout"
    [late_id] = res.json()["details"]["transaction_ids"]
    assert db.get(Stay, stay_id).status == "active"

    login(db, client, manager)
    rev = client.post(f"/stays/{stay_id}/folio/transactions/{late_id}/reverse", json={"reason": "Left 08:15"})
    assert rev.status_code == 201
    res = checkout_at(client, stay_id, left)
    assert res.status_code == 200
    assert (res.json()["folio"]["balance"], res.json()["folio"]["status"]) == ("0.00", "closed")


def test_checkout_time_in_the_future_is_rejected(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    res = checkout_at(client, stay_id, fake_clock.now() + timedelta(hours=1))
    assert res.status_code == 422
    assert res.json()["code"] == "checkout_in_future"


def test_checkout_time_before_check_in_is_rejected(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    fake_clock.advance(hours=1)
    res = checkout_at(client, stay_id, fake_clock.now() - timedelta(hours=2))
    assert res.status_code == 422
    assert res.json()["code"] == "checkout_before_check_in"


def test_checkout_time_without_timezone_is_rejected(db, client, tenant, receptionist):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    res = client.post(f"/stays/{stay_id}/checkout", json={"checkout_at": "2026-11-16T09:00:00"})
    assert res.status_code == 422


def test_checkout_time_before_a_room_change_is_rejected(db, client, tenant, manager, fake_clock):
    login(db, client, manager)
    stay_id, _ = check_in(db, client, tenant)
    other = make_room(db, tenant)
    db.commit()
    fake_clock.advance(hours=3)
    assert client.post(f"/stays/{stay_id}/change-room", json={"new_room_id": other.id}).status_code == 200
    fake_clock.advance(hours=1)
    res = checkout_at(client, stay_id, fake_clock.now() - timedelta(hours=2), backdate_reason="test")
    assert res.status_code == 422
    assert res.json()["code"] == "checkout_before_last_change"


def test_backdated_checkout_beyond_the_window_is_manager_only(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    pay(client, stay_id, "1000")
    fake_clock.advance(hours=6)
    res = checkout_at(client, stay_id, fake_clock.now() - timedelta(hours=3), backdate_reason="Forgot")
    assert res.status_code == 403
    assert res.json()["code"] == "backdate_not_allowed"


def test_manager_backdated_checkout_needs_a_reason_and_is_audited(db, client, tenant, manager, fake_clock):
    login(db, client, manager)
    stay_id, _ = check_in(db, client, tenant)
    pay(client, stay_id, "1000")
    fake_clock.advance(hours=6)
    left = fake_clock.now() - timedelta(hours=3)

    res = checkout_at(client, stay_id, left)
    assert res.status_code == 422
    assert (res.json()["code"], res.json()["details"]["field"]) == ("reason_required", "backdate_reason")

    res = checkout_at(client, stay_id, left, backdate_reason="Night shift forgot")
    assert res.status_code == 200
    [event] = db.query(AuditEvent).filter_by(action="stay.checked_out").all()
    assert event.reason == "Backdated: Night shift forgot"


# --- extend --------------------------------------------------------------------

def test_extend_sets_expected_checkout_and_is_audited(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    new_time = fake_clock.now() + timedelta(days=2)
    res = client.patch(f"/stays/{stay_id}/extend", json={"expected_checkout_at": new_time.isoformat()})
    assert res.status_code == 200
    assert datetime.fromisoformat(res.json()["expected_checkout_at"]) == new_time
    assert db.query(AuditEvent).filter_by(action="stay.extended").count() == 1


def test_extend_must_be_after_check_in(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    res = client.patch(f"/stays/{stay_id}/extend",
                       json={"expected_checkout_at": (fake_clock.now() - timedelta(hours=1)).isoformat()})
    assert res.json()["code"] == "invalid_expected_checkout"


def test_checked_out_stay_cannot_be_extended(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = check_in(db, client, tenant)
    pay(client, stay_id, "1000")
    client.post(f"/stays/{stay_id}/checkout")
    res = client.patch(f"/stays/{stay_id}/extend",
                       json={"expected_checkout_at": (fake_clock.now() + timedelta(days=1)).isoformat()})
    assert res.json()["code"] == "stay_not_active"
