"""Check-in API (M1 Day 2, task 3). The fake clock starts at Mon 2026-11-16 08:00 UTC."""
from datetime import datetime, timedelta

import pytest

from app.models import AuditEvent, FolioTransaction, Guest, Stay
from tests.factories import (
    add_override, daily_plan, log_in, make_guest, make_plan, make_room, make_room_type, make_stay,
    make_tenant, make_user,
)


@pytest.fixture
def tenant(db):
    return make_tenant(db)


@pytest.fixture
def freshup(db, tenant):
    return make_plan(db, tenant, name="Fresh-up", period_hours=2, grace_minutes=60)


@pytest.fixture
def room(db, tenant, freshup):
    # Capacity 3: Full day for 1-3 guests at 1000; Fresh-up for 1-2 guests at 500.
    room_type = make_room_type(db, tenant, capacity=3, daily_price="1000.00",
                               extra_rates={(freshup.id, 1): "500.00", (freshup.id, 2): "500.00"})
    return make_room(db, tenant, room_type=room_type, number="201")


@pytest.fixture
def receptionist(db, tenant):
    return make_user(db, tenant, role_code="receptionist")


@pytest.fixture
def manager(db, tenant):
    return make_user(db, tenant, role_code="manager")


def login(db, client, user):
    log_in(client, db, user)
    db.commit()  # so a failing request's rollback can't undo the setup
    return client


def payload(tenant_db_plan, room, **overrides):
    body = {
        "room_id": room.id, "stay_plan_id": tenant_db_plan.id, "occupancy": 2,
        "guest": {"full_name": "Ravi Kumar", "phone": "98765 43210"},
    }
    body.update(overrides)
    return body


# --- offers (plan picker) ------------------------------------------------

def test_offers_depend_on_occupancy(db, client, tenant, room, freshup, receptionist):
    login(db, client, receptionist)
    two = client.get(f"/rooms/{room.id}/offers", params={"occupancy": 2}).json()
    three = client.get(f"/rooms/{room.id}/offers", params={"occupancy": 3}).json()
    assert [(o["name"], o["listed_price"]) for o in two] == [("Full day", "1000.00"), ("Fresh-up", "500.00")]
    assert [o["name"] for o in three] == ["Full day"]


def test_inactive_plans_are_not_offered(db, client, tenant, room, freshup, receptionist):
    freshup.is_active = False
    login(db, client, receptionist)
    offers = client.get(f"/rooms/{room.id}/offers", params={"occupancy": 1}).json()
    assert [o["name"] for o in offers] == ["Full day"]


# --- happy path ----------------------------------------------------------

def test_check_in_creates_stay_folio_period_1_and_audit(db, client, tenant, room, receptionist, fake_clock):
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room))

    assert res.status_code == 201
    body = res.json()
    assert (body["room_number"], body["stay_plan_name"], body["occupancy"]) == ("201", "Full day", 2)
    assert (body["listed_price"], body["agreed_price"], body["discount_percent"]) == ("1000.00", "1000.00", "0.00")
    assert body["guest"]["phone"] == "+919876543210"
    assert (body["folio"]["status"], body["folio"]["balance"]) == ("open", "1000.00")
    assert (body["period_hours"], body["grace_minutes"]) == (24, 30)

    [charge] = db.query(FolioTransaction).filter_by(folio_id=body["folio"]["id"]).all()
    assert (charge.txn_type, charge.period_no, charge.created_by_user_id) == ("room_charge", 1, None)
    [event] = db.query(AuditEvent).filter_by(action="stay.checked_in").all()
    assert (event.actor_user_id, event.entity_id) == (receptionist.id, str(body["id"]))
    assert client.get(f"/rooms/{room.id}").json()["status"] == "occupied"


def test_expected_checkout_is_saved_and_shown_on_the_stay(db, client, tenant, room, receptionist, fake_clock):
    login(db, client, receptionist)
    expected = fake_clock.now() + timedelta(days=1)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, expected_checkout_at=expected.isoformat()))
    assert res.status_code == 201
    detail = client.get(f"/stays/{res.json()['id']}").json()
    assert datetime.fromisoformat(detail["expected_checkout_at"]) == expected


def test_expected_checkout_at_the_check_in_moment_is_rejected(db, client, tenant, room, receptionist, fake_clock):
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room,
                                             expected_checkout_at=fake_clock.now().isoformat()))
    assert res.status_code == 422
    assert res.json()["code"] == "invalid_expected_checkout"


def test_fresh_up_check_in_uses_the_plan_price_and_period(db, client, tenant, room, freshup, receptionist):
    login(db, client, receptionist)
    body = client.post("/stays", json=payload(freshup, room)).json()
    assert (body["listed_price"], body["period_hours"], body["grace_minutes"]) == ("500.00", 2, 60)
    assert body["folio"]["balance"] == "500.00"


# --- price -----------------------------------------------------------------

def test_receptionist_can_give_a_discount_without_a_reason(db, client, tenant, room, receptionist):
    login(db, client, receptionist)
    body = client.post("/stays", json=payload(daily_plan(db, tenant), room, agreed_price="850")).json()
    assert (body["agreed_price"], body["discount_percent"]) == ("850.00", "15.00")
    assert body["folio"]["balance"] == "850.00"


def test_discount_needs_the_override_permission(db, client, tenant, room, receptionist):
    add_override(db, receptionist, "stay.override_rate", "deny")
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, agreed_price="850"))
    assert res.status_code == 403
    assert res.json()["code"] == "override_rate_not_allowed"
    assert db.query(Stay).count() == 0


def test_price_above_listed_is_rejected(db, client, tenant, room, receptionist):
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, agreed_price="1100"))
    assert res.status_code == 422
    assert res.json()["code"] == "price_above_listed"


# --- room, plan, occupancy -----------------------------------------------------

def test_occupied_room_is_rejected(db, client, tenant, room, receptionist, manager):
    make_stay(db, tenant, manager, room=room)
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room))
    assert res.status_code == 409
    assert res.json()["code"] == "room_occupied"


def test_room_under_maintenance_is_rejected(db, client, tenant, room, receptionist):
    room.operational_status = "maintenance"
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room))
    assert res.status_code == 409
    assert res.json()["code"] == "room_not_available"


def test_occupancy_above_capacity_is_rejected(db, client, tenant, room, receptionist):
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, occupancy=4))
    assert res.json()["code"] == "occupancy_exceeds_capacity"


def test_plan_without_a_rate_for_this_occupancy_is_rejected(db, client, tenant, room, freshup, receptionist):
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(freshup, room, occupancy=3))
    assert res.status_code == 422
    assert res.json()["code"] == "plan_not_offered"


# --- guest -------------------------------------------------------------------

def test_guest_lookup_and_reuse(db, client, tenant, room, receptionist):
    existing = make_guest(db, tenant, phone="+919876543210")
    login(db, client, receptionist)
    found = client.get("/guests", params={"phone": "098765-43210"}).json()
    assert [g["id"] for g in found] == [existing.id]

    body = payload(daily_plan(db, tenant), room, guest_id=existing.id)
    del body["guest"]
    res = client.post("/stays", json=body)
    assert res.status_code == 201
    assert res.json()["guest"]["id"] == existing.id
    assert db.query(Guest).filter_by(tenant_id=tenant.id).count() == 1


def test_another_tenants_guest_is_not_found(db, client, tenant, room, receptionist):
    foreign = make_guest(db, make_tenant(db))
    login(db, client, receptionist)
    body = payload(daily_plan(db, tenant), room, guest_id=foreign.id)
    del body["guest"]
    res = client.post("/stays", json=body)
    assert res.status_code == 404
    assert res.json()["code"] == "guest_not_found"


def test_guest_id_and_guest_together_is_a_request_error(db, client, tenant, room, receptionist):
    existing = make_guest(db, tenant)
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, guest_id=existing.id))
    assert res.status_code == 422


def test_failed_check_in_leaves_nothing_behind(db, client, tenant, room, receptionist):
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room,
                                             guest={"full_name": "X", "phone": "12"}))
    assert res.json()["code"] == "invalid_phone"
    assert db.query(Stay).count() == 0
    assert db.query(Guest).count() == 0


# --- time --------------------------------------------------------------------

def test_time_without_timezone_is_rejected(db, client, tenant, room, receptionist):
    login(db, client, receptionist)
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, check_in_at="2026-11-16T07:00:00"))
    assert res.status_code == 422


def test_future_check_in_is_rejected(db, client, tenant, room, receptionist, fake_clock):
    login(db, client, receptionist)
    future = (fake_clock.now() + timedelta(hours=1)).isoformat()
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, check_in_at=future))
    assert res.json()["code"] == "check_in_in_future"


def test_backdate_within_the_window_needs_nothing_extra(db, client, tenant, room, receptionist, fake_clock):
    login(db, client, receptionist)
    earlier = (fake_clock.now() - timedelta(minutes=90)).isoformat()
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, check_in_at=earlier))
    assert res.status_code == 201


def test_backdate_beyond_the_window_is_manager_only(db, client, tenant, room, receptionist, fake_clock):
    login(db, client, receptionist)
    earlier = (fake_clock.now() - timedelta(hours=3)).isoformat()
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, check_in_at=earlier,
                                             backdate_reason="Arrived at 5am, entered late"))
    assert res.status_code == 403
    assert res.json()["code"] == "backdate_not_allowed"


def test_manager_backdate_needs_a_reason(db, client, tenant, room, manager, fake_clock):
    login(db, client, manager)
    earlier = (fake_clock.now() - timedelta(hours=3)).isoformat()
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, check_in_at=earlier))
    assert res.status_code == 422
    assert res.json()["code"] == "reason_required"


def test_backdate_over_30_days_is_rejected_even_for_a_manager(db, client, tenant, room, manager, fake_clock):
    login(db, client, manager)
    too_old = (fake_clock.now() - timedelta(days=31)).isoformat()
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, check_in_at=too_old,
                                             backdate_reason="typo test"))
    assert res.status_code == 422
    assert res.json()["code"] == "check_in_too_old"


def test_long_backdate_posts_the_periods_already_due(db, client, tenant, room, manager, fake_clock):
    login(db, client, manager)
    earlier = (fake_clock.now() - timedelta(hours=26)).isoformat()  # Sun 06:00: day 2 due Mon 06:30
    res = client.post("/stays", json=payload(daily_plan(db, tenant), room, check_in_at=earlier,
                                             backdate_reason="Night shift forgot to enter"))
    assert res.status_code == 201
    assert res.json()["folio"]["balance"] == "2000.00"
    [event] = db.query(AuditEvent).filter_by(action="stay.checked_in").all()
    assert "Night shift forgot to enter" in event.reason
