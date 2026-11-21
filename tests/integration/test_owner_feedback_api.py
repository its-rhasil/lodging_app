"""Backend additions from the owner's browser testing (2026-11-18): stay plan delete, user
reactivation, the permission catalogue, and price correction. Fake clock: Mon 2026-11-16 08:00 UTC."""
import pytest

from app.models import AuditEvent, RoomTypeRate, StayPlan
from tests.factories import (
    DEFAULT_PASSWORD, daily_plan, log_in, make_plan, make_room, make_room_type, make_stay, make_tenant,
    make_user,
)


@pytest.fixture
def tenant(db):
    return make_tenant(db)


@pytest.fixture
def admin(db, tenant):
    return make_user(db, tenant, role_code="tenant_admin")


@pytest.fixture
def manager(db, tenant):
    return make_user(db, tenant, role_code="manager")


@pytest.fixture
def receptionist(db, tenant):
    return make_user(db, tenant, role_code="receptionist")


def login(db, client, user):
    log_in(client, db, user)
    db.commit()


# --- stay plan delete ------------------------------------------------------------

def test_unused_plan_is_deleted_with_its_rates(db, client, tenant, admin):
    plan = make_plan(db, tenant, name="Hourly", period_hours=1, grace_minutes=10)
    room_type = make_room_type(db, tenant, capacity=1, extra_rates={(plan.id, 1): "200.00"})
    plan_id = plan.id
    login(db, client, admin)

    assert client.delete(f"/stay-plans/{plan_id}").status_code == 204
    assert db.get(StayPlan, plan_id) is None
    assert db.query(RoomTypeRate).filter_by(room_type_id=room_type.id, stay_plan_id=plan_id).count() == 0
    assert db.query(AuditEvent).filter_by(action="stay_plan.deleted").count() == 1


def test_used_plan_cannot_be_deleted(db, client, tenant, admin):
    plan = make_plan(db, tenant)
    make_stay(db, tenant, admin, plan=plan)
    login(db, client, admin)
    res = client.delete(f"/stay-plans/{plan.id}")
    assert res.status_code == 409
    assert res.json()["code"] == "stay_plan_in_use"


def test_daily_plan_cannot_be_deleted(db, client, tenant, admin):
    login(db, client, admin)
    res = client.delete(f"/stay-plans/{daily_plan(db, tenant).id}")
    assert res.json()["code"] == "daily_plan_required"


# --- users -----------------------------------------------------------------------

def test_reactivated_user_can_log_in_again(db, client, tenant, admin, receptionist):
    login(db, client, admin)
    client.post(f"/users/{receptionist.id}/deactivate")
    res = client.post(f"/users/{receptionist.id}/reactivate")
    assert (res.status_code, res.json()["is_active"]) == (200, True)
    assert db.query(AuditEvent).filter_by(action="user.reactivated").count() == 1

    client.cookies.clear()
    assert client.post("/auth/login", json={"email": receptionist.email,
                                            "password": DEFAULT_PASSWORD}).status_code == 200


def test_permission_catalogue_lists_default_roles(db, client, tenant, admin, manager):
    login(db, client, admin)
    rows = {p["code"]: p for p in client.get("/users/permission-catalogue").json()}
    assert rows["payment.refund"]["roles"] == ["manager", "tenant_admin"]
    assert rows["folio.waive"]["roles"] == ["manager", "receptionist", "tenant_admin"]

    login(db, client, manager)
    assert client.get("/users/permission-catalogue").status_code == 403


def test_admin_grants_and_removes_a_permission(db, client, tenant, admin, receptionist):
    login(db, client, admin)
    res = client.put(f"/users/{receptionist.id}/overrides",
                     json={"overrides": [{"permission_code": "payment.refund", "effect": "grant"}]})
    assert "payment.refund" in res.json()["permissions"]
    res = client.put(f"/users/{receptionist.id}/overrides", json={"overrides": []})
    assert "payment.refund" not in res.json()["permissions"]


# --- cancel a check-in ------------------------------------------------------------------

def _check_in(db, client, tenant):
    room = make_room(db, tenant, room_type=make_room_type(db, tenant, capacity=2, daily_price="1000.00"))
    db.commit()
    res = client.post("/stays", json={"room_id": room.id, "stay_plan_id": daily_plan(db, tenant).id,
                                      "occupancy": 1, "guest": {"full_name": "Ravi", "phone": "9876543210"}})
    assert res.status_code == 201, res.json()
    return res.json()["id"], room.id


def test_receptionist_cancels_within_30_minutes(db, client, tenant, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id, room_id = _check_in(db, client, tenant)
    fake_clock.advance(minutes=29)

    res = client.post(f"/stays/{stay_id}/cancel", json={"reason": "Wrong room"})
    assert res.status_code == 200
    body = res.json()
    assert (body["status"], body["folio"]["status"], body["folio"]["balance"]) == ("cancelled", "closed", "0.00")
    assert client.get(f"/rooms/{room_id}").json()["status"] == "available"
    assert db.query(AuditEvent).filter_by(action="stay.cancelled").one().reason == "Wrong room"

    # The room can be checked into again, and the cancelled stay accepts no more actions.
    again = client.post("/stays", json={"room_id": room_id, "stay_plan_id": daily_plan(db, tenant).id,
                                        "occupancy": 1, "guest": {"full_name": "Asha", "phone": "9000000001"}})
    assert again.status_code == 201
    assert client.post(f"/stays/{stay_id}/checkout").json()["code"] == "stay_not_active"


def test_after_30_minutes_only_a_manager_cancels(db, client, tenant, receptionist, manager, fake_clock):
    login(db, client, receptionist)
    stay_id, _ = _check_in(db, client, tenant)
    fake_clock.advance(minutes=31)
    res = client.post(f"/stays/{stay_id}/cancel", json={"reason": "Guest left"})
    assert res.status_code == 403
    assert res.json()["code"] == "cancel_window_passed"

    login(db, client, manager)
    assert client.post(f"/stays/{stay_id}/cancel", json={"reason": "Guest left"}).status_code == 200


def test_cancel_is_blocked_while_a_payment_stands(db, client, tenant, manager):
    import uuid
    login(db, client, manager)
    stay_id, _ = _check_in(db, client, tenant)
    folio = client.post(f"/stays/{stay_id}/folio/payments", json={
        "amount": "500", "method": "cash", "idempotency_key": str(uuid.uuid4())}).json()
    res = client.post(f"/stays/{stay_id}/cancel", json={"reason": "x"})
    assert res.status_code == 409
    assert res.json()["code"] == "payment_taken"

    payment = [t for t in folio["transactions"] if t["txn_type"] == "payment"][0]["id"]
    client.post(f"/stays/{stay_id}/folio/transactions/{payment}/reverse", json={"reason": "Taken by mistake"})
    assert client.post(f"/stays/{stay_id}/cancel", json={"reason": "x"}).json()["folio"]["balance"] == "0.00"


def test_cancel_reverses_waived_and_extra_charges(db, client, tenant, receptionist):
    login(db, client, receptionist)
    stay_id, _ = _check_in(db, client, tenant)
    folio = client.post(f"/stays/{stay_id}/folio/charges", json={"amount": "250", "description": "Tea"}).json()
    day_1 = [t for t in folio["transactions"] if t["txn_type"] == "room_charge"][0]["id"]
    client.post(f"/stays/{stay_id}/folio/transactions/{day_1}/waive", json={"amount": "100", "reason": "Regular"})
    body = client.post(f"/stays/{stay_id}/cancel", json={"reason": "Wrong guest"}).json()
    assert (body["status"], body["folio"]["balance"]) == ("cancelled", "0.00")


# --- price correction -----------------------------------------------------------------

def _converted_at_price(db, client, tenant, price):
    """The owner's case: a fresh-up stay converted to full day with 8 typed by mistake."""
    freshup = make_plan(db, tenant, name="Fresh-up", period_hours=2, grace_minutes=60)
    room = make_room(db, tenant, room_type=make_room_type(db, tenant, capacity=2, daily_price="1000.00",
                                                         extra_rates={(freshup.id, 1): "500.00"}))
    db.commit()
    stay_id = client.post("/stays", json={
        "room_id": room.id, "stay_plan_id": freshup.id, "occupancy": 1,
        "guest": {"full_name": "Ravi", "phone": "9876543210"},
    }).json()["id"]
    body = client.post(f"/stays/{stay_id}/convert-to-daily", json={"agreed_price": price}).json()
    assert body["folio"]["balance"] == "8.00"
    return stay_id


def test_wrong_price_after_conversion_can_be_corrected(db, client, tenant, manager, fake_clock):
    login(db, client, manager)
    stay_id = _converted_at_price(db, client, tenant, "8")

    res = client.post(f"/stays/{stay_id}/correct-price", json={"agreed_price": "1000", "reason": "Typed 8 by mistake"})
    assert res.status_code == 200
    body = res.json()
    assert (body["agreed_price"], body["folio"]["balance"]) == ("1000.00", "1000.00")

    folio = client.get(f"/stays/{stay_id}/folio").json()
    corrected = [t for t in folio["transactions"] if t["txn_type"] == "room_charge" and not t["is_reversed"]]
    assert [(t["amount"], t["period_no"]) for t in corrected] == [("1000.00", 1)]

    fake_clock.advance(hours=24, minutes=30)  # day 2 posts at the corrected price, once
    folio = client.get(f"/stays/{stay_id}/folio").json()
    live = [t for t in folio["transactions"] if t["txn_type"] == "room_charge" and not t["is_reversed"]]
    assert [(t["amount"], t["period_no"]) for t in live] == [("1000.00", 1), ("1000.00", 2)]
    assert db.query(AuditEvent).filter_by(action="stay.price_corrected").one().reason == "Typed 8 by mistake"


def test_price_correction_rules(db, client, tenant, manager, receptionist):
    login(db, client, manager)
    stay_id = _converted_at_price(db, client, tenant, "8")
    above = client.post(f"/stays/{stay_id}/correct-price", json={"agreed_price": "1200", "reason": "x"})
    assert above.json()["code"] == "price_above_listed"
    same = client.post(f"/stays/{stay_id}/correct-price", json={"agreed_price": "8", "reason": "x"})
    assert same.json()["code"] == "price_unchanged"
    blank = client.post(f"/stays/{stay_id}/correct-price", json={"agreed_price": "900", "reason": "  "})
    assert blank.json()["code"] == "reason_required"

    login(db, client, receptionist)
    assert client.post(f"/stays/{stay_id}/correct-price",
                       json={"agreed_price": "1000", "reason": "x"}).status_code == 403
