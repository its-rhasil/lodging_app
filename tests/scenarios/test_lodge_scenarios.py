"""End-to-end lodge scenarios through the API (testing-strategy.md §11, M1 Day 3 acceptance).

The fake clock starts at Mon 2026-11-16 08:00 UTC ("day 1, 08:00").
"""
import uuid
from datetime import timedelta

import pytest

from app.models import AuditEvent, FolioTransaction
from app.service import tenant_service
from tests.factories import (
    daily_plan, log_in, make_plan, make_room, make_room_type, make_tenant, make_user,
)


@pytest.fixture
def tenant(db):
    return make_tenant(db)


@pytest.fixture
def receptionist(db, tenant):
    return make_user(db, tenant, role_code="receptionist")


@pytest.fixture
def manager(db, tenant):
    return make_user(db, tenant, role_code="manager")


def as_user(db, client, user):
    log_in(client, db, user)
    db.commit()


def room(db, tenant, price="1000.00", number=None, extra_rates=None):
    return make_room(db, tenant, number=number,
                     room_type=make_room_type(db, tenant, capacity=2, daily_price=price, extra_rates=extra_rates))


def check_in(client, room_id, plan_id, **extra):
    body = {"room_id": room_id, "stay_plan_id": plan_id, "occupancy": 1,
            "guest": {"full_name": "Ravi Kumar", "phone": "9876543210"}, **extra}
    res = client.post("/stays", json=body)
    assert res.status_code == 201, res.json()
    return res.json()["id"]


def pay(client, stay_id, amount, method="cash"):
    res = client.post(f"/stays/{stay_id}/folio/payments",
                      json={"amount": amount, "method": method, "idempotency_key": str(uuid.uuid4())})
    assert res.status_code in (200, 201), res.json()
    return res.json()


def folio(client, stay_id):
    return client.get(f"/stays/{stay_id}/folio").json()


def room_charges(folio_body):
    return [t for t in folio_body["transactions"] if t["txn_type"] == "room_charge"]


# 1
def test_regular_stay_inside_the_grace(db, client, tenant, receptionist, fake_clock):
    as_user(db, client, receptionist)
    stay = check_in(client, room(db, tenant).id, daily_plan(db, tenant).id)
    fake_clock.advance(hours=24, minutes=20)
    pay(client, stay, "1000", method="upi")
    res = client.post(f"/stays/{stay}/checkout")
    assert (res.json()["folio"]["balance"], res.json()["folio"]["status"]) == ("0.00", "closed")
    assert len(room_charges(folio(client, stay))) == 1


# 2
def test_late_checkout_with_a_waiver(db, client, tenant, receptionist, fake_clock):
    as_user(db, client, receptionist)
    stay = check_in(client, room(db, tenant).id, daily_plan(db, tenant).id)
    fake_clock.advance(hours=26)  # day 2, 10:00
    day_2 = room_charges(folio(client, stay))[1]["id"]
    client.post(f"/stays/{stay}/folio/transactions/{day_2}/waive", json={"amount": "1000", "reason": "Late bus"})
    pay(client, stay, "1000")
    assert client.post(f"/stays/{stay}/checkout").json()["folio"]["balance"] == "0.00"
    assert db.query(AuditEvent).filter_by(action="folio.waived").one().reason == "Late bus"


# 3
def test_multi_day_stay_with_a_room_change(db, client, tenant, receptionist, fake_clock):
    as_user(db, client, receptionist)
    old_room, new_room = room(db, tenant, "1000.00", "101"), room(db, tenant, "1500.00", "201")
    stay = check_in(client, old_room.id, daily_plan(db, tenant).id)
    fake_clock.advance(hours=31)  # day 2, 15:00
    client.post(f"/stays/{stay}/change-room", json={"new_room_id": new_room.id})
    fake_clock.advance(hours=42)  # day 4, 09:00
    body = folio(client, stay)
    assert [c["amount"] for c in room_charges(body)] == ["1000.00", "1000.00", "1500.00", "1500.00"]
    assert client.get(f"/rooms/{old_room.id}").json()["status"] == "cleaning"


# 4
def test_fresh_up_3h_then_conversion(db, client, tenant, receptionist, fake_clock):
    freshup = make_plan(db, tenant, name="Fresh-up", period_hours=3, grace_minutes=15)
    r = room(db, tenant, "1200.00", extra_rates={(freshup.id, 1): "500.00"})
    fake_clock.advance(hours=6)  # 14:00
    as_user(db, client, receptionist)
    stay = check_in(client, r.id, freshup.id)
    fake_clock.advance(hours=3, minutes=16)  # 17:16
    assert len(room_charges(folio(client, stay))) == 2
    converted = client.post(f"/stays/{stay}/convert-to-daily").json()
    assert converted["folio"]["balance"] == "1200.00"
    fake_clock.set(fake_clock.now().replace(hour=14, minute=29) + timedelta(days=1))
    assert folio(client, stay)["balance"] == "1200.00"
    fake_clock.advance(minutes=1)  # next day 14:30
    assert folio(client, stay)["balance"] == "2400.00"


# 4b
@pytest.mark.parametrize("leave_after,hours_charged", [(timedelta(hours=2, minutes=5), 2),
                                                        (timedelta(hours=2, minutes=15), 3)])
def test_hourly_plan(db, client, tenant, receptionist, fake_clock, leave_after, hours_charged):
    hourly = make_plan(db, tenant, name="Hourly", period_hours=1, grace_minutes=10)
    r = room(db, tenant, extra_rates={(hourly.id, 1): "200.00"})
    as_user(db, client, receptionist)
    stay = check_in(client, r.id, hourly.id)
    fake_clock.advance(seconds=leave_after.total_seconds())
    pay(client, stay, str(200 * hours_charged))
    res = client.post(f"/stays/{stay}/checkout")
    assert res.status_code == 200, res.json()
    assert len(room_charges(folio(client, stay))) == hours_charged


# 4c
def test_lodge_without_short_stays_offers_only_full_day(db, client, tenant, receptionist):
    r = room(db, tenant)
    as_user(db, client, receptionist)
    offers = client.get(f"/rooms/{r.id}/offers", params={"occupancy": 1}).json()
    assert [o["name"] for o in offers] == ["Full day"]


# 5
def test_forced_checkout_and_pending_balance(db, client, tenant, receptionist, manager):
    as_user(db, client, receptionist)
    stay = check_in(client, room(db, tenant).id, daily_plan(db, tenant).id)
    assert client.post(f"/stays/{stay}/checkout").status_code == 403

    as_user(db, client, manager)
    assert client.post(f"/stays/{stay}/checkout", json={"force_reason": "Pays by UPI tonight"}).status_code == 200
    assert [r["id"] for r in client.get("/stays/pending-balances").json()] == [stay]

    as_user(db, client, receptionist)
    assert pay(client, stay, "1000")["status"] == "closed"
    assert client.get("/stays/pending-balances").json() == []


# 6
def test_overpayment_needs_a_refund_before_checkout(db, client, tenant, manager):
    as_user(db, client, manager)
    stay = check_in(client, room(db, tenant).id, daily_plan(db, tenant).id)
    pay(client, stay, "1200")
    assert client.post(f"/stays/{stay}/checkout").json()["code"] == "refund_required"
    client.post(f"/stays/{stay}/folio/refunds", json={"amount": "200", "method": "cash", "reason": "Change"})
    assert client.post(f"/stays/{stay}/checkout").json()["folio"]["balance"] == "0.00"


# 7
def test_wrong_charge_is_reversed_and_both_rows_remain(db, client, tenant, manager):
    as_user(db, client, manager)
    stay = check_in(client, room(db, tenant).id, daily_plan(db, tenant).id)
    body = client.post(f"/stays/{stay}/folio/charges", json={"amount": "300", "description": "Laundry"}).json()
    charge = [t for t in body["transactions"] if t["txn_type"] == "charge"][0]["id"]
    body = client.post(f"/stays/{stay}/folio/transactions/{charge}/reverse", json={"reason": "Wrong room"}).json()
    types = [t["txn_type"] for t in body["transactions"]]
    assert types == ["room_charge", "charge", "reversal"]
    assert body["balance"] == "1000.00"


# 8
def test_backdated_check_in(db, client, tenant, receptionist, manager, fake_clock):
    plan = daily_plan(db, tenant)
    r1, r2 = room(db, tenant), room(db, tenant)
    as_user(db, client, receptionist)
    check_in(client, r1.id, plan.id, check_in_at=(fake_clock.now() - timedelta(minutes=30)).isoformat())
    five_hours_back = (fake_clock.now() - timedelta(hours=5)).isoformat()
    assert client.post("/stays", json={"room_id": r2.id, "stay_plan_id": plan.id, "occupancy": 1,
                                       "guest": {"full_name": "B", "phone": "9000000009"},
                                       "check_in_at": five_hours_back}).status_code == 403
    as_user(db, client, manager)
    check_in(client, r2.id, plan.id, check_in_at=five_hours_back, backdate_reason="Arrived at 3am")


# 9
def test_nobody_looks_for_two_days(db, client, tenant, receptionist, fake_clock):
    as_user(db, client, receptionist)
    stay = check_in(client, room(db, tenant).id, daily_plan(db, tenant).id)
    check_in_at = fake_clock.now()
    fake_clock.advance(days=2, hours=1)
    charges = room_charges(folio(client, stay))
    assert [c["period_no"] for c in charges] == [1, 2, 3]
    starts = [db.get(FolioTransaction, c["id"]).period_start_at for c in charges]
    assert starts == [check_in_at + timedelta(days=n) for n in range(3)]


# 10
def test_tenant_onboarding_to_first_check_in(db, client):
    tenant, _ = tenant_service.create_tenant(
        db, name="Sea View Lodge", contact_email="owner@seaview.example", contact_phone="9000000000",
        address=None, admin_email="admin@seaview.example", admin_name="Owner", admin_password="longenough1",
    )
    assert client.post("/auth/login", json={"email": "admin@seaview.example",
                                            "password": "longenough1"}).status_code == 200
    plan_id = client.get("/stay-plans").json()[0]["id"]
    room_type = client.post("/room-types", json={"name": "Standard", "capacity": 2, "rates": [
        {"stay_plan_id": plan_id, "occupancy": 1, "price": "900"},
        {"stay_plan_id": plan_id, "occupancy": 2, "price": "1100"}]}).json()
    room_id = client.post("/rooms", json={"room_type_id": room_type["id"], "room_number": "1"}).json()["id"]
    client.post("/users", json={"email": "desk@seaview.example", "name": "Desk", "password": "longenough1",
                                "role_code": "receptionist"})

    client.cookies.clear()
    client.post("/auth/login", json={"email": "desk@seaview.example", "password": "longenough1"})
    stay = check_in(client, room_id, plan_id)
    assert folio(client, stay)["balance"] == "900.00"


# 11
def test_deactivation_mid_shift(db, client, tenant, receptionist):
    admin = make_user(db, tenant, role_code="tenant_admin")
    desk_token = log_in(client, db, receptionist)
    db.commit()
    assert client.get("/dashboard").status_code == 200

    as_user(db, client, admin)
    assert client.post(f"/users/{receptionist.id}/deactivate").status_code == 200

    client.cookies.set("access_token", desk_token)
    assert client.get("/dashboard").status_code == 401
    assert db.query(AuditEvent).filter_by(action="user.deactivated").count() == 1
