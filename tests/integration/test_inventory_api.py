"""Inventory API: stay plans, room types + rates, rooms, room status (M1 Day 2, slices A-B)."""
import pytest

from app.models import AuditEvent, Room, RoomTypeRate, StayPlan
from tests.factories import (
    daily_plan, log_in, make_plan, make_room, make_room_type, make_stay, make_tenant, make_user,
)


@pytest.fixture
def tenant(db):
    return make_tenant(db)


@pytest.fixture
def admin(db, tenant):
    return make_user(db, tenant, role_code="tenant_admin")


@pytest.fixture
def receptionist(db, tenant):
    return make_user(db, tenant, role_code="receptionist")


def login(db, client, user):
    """Log in and commit the setup, so a failing request's rollback can't undo it."""
    log_in(client, db, user)
    db.commit()
    return client


def audits(db, action):
    return db.query(AuditEvent).filter_by(action=action).all()


# --- stay plans ----------------------------------------------------------

def test_receptionist_lists_plans_but_cannot_create(db, client, tenant, receptionist):
    login(db, client, receptionist)
    res = client.get("/stay-plans")
    assert res.status_code == 200
    assert [p["name"] for p in res.json()] == ["Full day"]
    assert client.post("/stay-plans", json={"name": "Fresh-up", "period_hours": 2}).status_code == 403


def test_admin_creates_a_non_daily_plan(db, client, tenant, admin):
    login(db, client, admin)
    res = client.post("/stay-plans", json={"name": " Fresh-up ", "period_hours": 2, "grace_minutes": 60})
    assert res.status_code == 201
    body = res.json()
    assert (body["name"], body["period_hours"], body["grace_minutes"], body["is_daily"], body["is_active"]) == (
        "Fresh-up", 2, 60, False, True)
    assert len(audits(db, "stay_plan.created")) == 1


def test_plan_names_are_unique_ignoring_case(db, client, tenant, admin):
    make_plan(db, tenant, name="Fresh-up")
    login(db, client, admin)
    res = client.post("/stay-plans", json={"name": "FRESH-UP", "period_hours": 3})
    assert res.status_code == 409
    assert res.json()["code"] == "stay_plan_name_taken"


@pytest.mark.parametrize("change,code", [
    ({"period_hours": 12}, "daily_plan_period_fixed"),
    ({"is_active": False}, "daily_plan_always_active"),
])
def test_daily_plan_stays_24h_and_active(db, client, tenant, admin, change, code):
    plan_id = daily_plan(db, tenant).id
    login(db, client, admin)
    res = client.patch(f"/stay-plans/{plan_id}", json=change)
    assert res.status_code == 422
    assert res.json()["code"] == code


def test_daily_plan_grace_can_change_and_is_audited(db, client, tenant, admin):
    plan_id = daily_plan(db, tenant).id
    login(db, client, admin)
    res = client.patch(f"/stay-plans/{plan_id}", json={"grace_minutes": 45})
    assert res.status_code == 200
    assert res.json()["grace_minutes"] == 45
    [event] = audits(db, "stay_plan.updated")
    assert event.changes == {"grace_minutes": [30, 45]}


def test_saving_without_changes_writes_no_audit(db, client, tenant, admin):
    plan_id = daily_plan(db, tenant).id
    login(db, client, admin)
    assert client.patch(f"/stay-plans/{plan_id}", json={"grace_minutes": 30}).status_code == 200
    assert audits(db, "stay_plan.updated") == []


def test_other_plans_can_be_deactivated(db, client, tenant, admin):
    plan = make_plan(db, tenant)
    login(db, client, admin)
    assert client.patch(f"/stay-plans/{plan.id}", json={"is_active": False}).json()["is_active"] is False


def test_another_tenants_plan_is_not_found(db, client, tenant, admin):
    other_plan = daily_plan(db, make_tenant(db))
    login(db, client, admin)
    res = client.patch(f"/stay-plans/{other_plan.id}", json={"grace_minutes": 10})
    assert res.status_code == 404
    assert res.json()["code"] == "stay_plan_not_found"


# --- room types and rates ------------------------------------------------

def _rates(plan_id, prices: dict[int, str]):
    return [{"stay_plan_id": plan_id, "occupancy": occ, "price": price} for occ, price in prices.items()]


def test_admin_creates_room_type_with_rates(db, client, tenant, admin):
    daily, freshup = daily_plan(db, tenant), make_plan(db, tenant)
    login(db, client, admin)
    res = client.post("/room-types", json={
        "name": "Deluxe", "capacity": 3,
        "rates": _rates(daily.id, {1: "1000", 2: "1200", 3: "1500"}) + _rates(freshup.id, {1: "500", 2: "500"}),
    })
    assert res.status_code == 201
    body = res.json()
    assert (body["name"], body["capacity"], body["is_active"]) == ("Deluxe", 3, True)
    assert len(body["rates"]) == 5
    [event] = audits(db, "room_type.created")
    assert "plan %d x3 = 1500.00" % daily.id in event.changes["rates"][1]


def test_room_type_needs_full_daily_rates(db, client, tenant, admin):
    daily = daily_plan(db, tenant)
    login(db, client, admin)
    res = client.post("/room-types", json={"name": "Deluxe", "capacity": 3,
                                           "rates": _rates(daily.id, {1: "1000"})})
    assert res.status_code == 422
    assert res.json()["details"]["missing_occupancies"] == [2, 3]


def test_receptionist_cannot_create_room_types(db, client, tenant, receptionist):
    daily = daily_plan(db, tenant)
    login(db, client, receptionist)
    res = client.post("/room-types", json={"name": "X", "capacity": 1, "rates": _rates(daily.id, {1: "1000"})})
    assert res.status_code == 403


def test_negative_price_is_a_request_error(db, client, tenant, admin):
    daily = daily_plan(db, tenant)
    login(db, client, admin)
    res = client.post("/room-types", json={"name": "X", "capacity": 1, "rates": _rates(daily.id, {1: "-5"})})
    assert res.status_code == 422
    assert res.json()["code"] == "invalid_request"


def test_lowering_capacity_needs_matching_rates(db, client, tenant, admin):
    room_type = make_room_type(db, tenant, capacity=3)
    daily = daily_plan(db, tenant)
    login(db, client, admin)

    res = client.patch(f"/room-types/{room_type.id}", json={"capacity": 2})
    assert res.status_code == 422
    assert res.json()["code"] == "occupancy_exceeds_capacity"

    res = client.patch(f"/room-types/{room_type.id}", json={
        "capacity": 2, "rates": _rates(daily.id, {1: "900", 2: "1100"}),
    })
    assert res.status_code == 200
    assert [(r["occupancy"], r["price"]) for r in res.json()["rates"]] == [(1, "900.00"), (2, "1100.00")]
    assert db.query(RoomTypeRate).filter_by(room_type_id=room_type.id).count() == 2
    [event] = audits(db, "room_type.updated")
    assert event.changes["capacity"] == [3, 2]


def test_room_type_names_are_unique(db, client, tenant, admin):
    first, second = make_room_type(db, tenant), make_room_type(db, tenant)
    login(db, client, admin)
    res = client.patch(f"/room-types/{second.id}", json={"name": first.name})
    assert res.status_code == 409
    assert res.json()["code"] == "room_type_name_taken"


def test_rates_cannot_use_another_tenants_plan(db, client, tenant, admin):
    daily = daily_plan(db, tenant)
    other_plan = make_plan(db, make_tenant(db))
    login(db, client, admin)
    res = client.post("/room-types", json={
        "name": "X", "capacity": 1, "rates": _rates(daily.id, {1: "1000"}) + _rates(other_plan.id, {1: "500"}),
    })
    assert res.status_code == 404


def test_room_type_list_is_tenant_scoped(db, client, tenant, receptionist):
    mine = make_room_type(db, tenant)
    make_room_type(db, make_tenant(db))
    login(db, client, receptionist)
    assert [t["id"] for t in client.get("/room-types").json()] == [mine.id]


# --- rooms ---------------------------------------------------------------

def test_admin_creates_room_with_string_number(db, client, tenant, admin):
    room_type = make_room_type(db, tenant)
    login(db, client, admin)
    res = client.post("/rooms", json={"room_type_id": room_type.id, "room_number": " A-12 "})
    assert res.status_code == 201
    body = res.json()
    assert (body["room_number"], body["status"], body["room_type_name"]) == ("A-12", "available", room_type.name)
    assert len(audits(db, "room.created")) == 1


def test_room_numbers_are_unique(db, client, tenant, admin):
    room = make_room(db, tenant, number="101")
    login(db, client, admin)
    res = client.post("/rooms", json={"room_type_id": room.room_type_id, "room_number": "101"})
    assert res.status_code == 409
    assert res.json()["code"] == "room_number_taken"


def test_room_needs_an_active_room_type_of_this_tenant(db, client, tenant, admin):
    inactive = make_room_type(db, tenant)
    inactive.is_active = False
    foreign = make_room_type(db, make_tenant(db))
    login(db, client, admin)
    assert client.post("/rooms", json={"room_type_id": inactive.id, "room_number": "1"}).json()["code"] == (
        "room_type_inactive")
    assert client.post("/rooms", json={"room_type_id": foreign.id, "room_number": "2"}).status_code == 404


def test_room_list_shows_occupied_rooms(db, client, tenant, admin, receptionist):
    free = make_room(db, tenant, number="101")
    taken = make_room(db, tenant, number="102")
    stay = make_stay(db, tenant, admin, room=taken)
    login(db, client, receptionist)
    rows = {r["room_number"]: r for r in client.get("/rooms").json()}
    assert (rows["101"]["status"], rows["101"]["active_stay_id"]) == ("available", None)
    assert (rows["102"]["status"], rows["102"]["active_stay_id"]) == ("occupied", stay.id)
    assert client.get(f"/rooms/{free.id}").json()["status"] == "available"


@pytest.mark.parametrize("change", ["room_type", "deactivate"])
def test_occupied_room_cannot_change_type_or_be_deactivated(db, client, tenant, admin, change):
    room = make_room(db, tenant)
    make_stay(db, tenant, admin, room=room)
    other_type = make_room_type(db, tenant)
    login(db, client, admin)
    body = {"room_type_id": other_type.id} if change == "room_type" else {"is_active": False}
    res = client.patch(f"/rooms/{room.id}", json=body)
    assert res.status_code == 409
    assert res.json()["code"] == "room_occupied"


def test_occupied_room_can_be_renumbered(db, client, tenant, admin):
    room = make_room(db, tenant, number="101")
    make_stay(db, tenant, admin, room=room)
    login(db, client, admin)
    res = client.patch(f"/rooms/{room.id}", json={"room_number": "101A"})
    assert res.status_code == 200
    assert res.json()["room_number"] == "101A"


def test_another_tenants_room_is_not_found(db, client, tenant, admin):
    foreign = make_room(db, make_tenant(db))
    login(db, client, admin)
    assert client.get(f"/rooms/{foreign.id}").status_code == 404
    assert client.patch(f"/rooms/{foreign.id}", json={"room_number": "9"}).status_code == 404


# --- room status ---------------------------------------------------------

def test_receptionist_changes_room_status_and_it_is_audited(db, client, tenant, receptionist):
    room = make_room(db, tenant)
    login(db, client, receptionist)
    res = client.patch(f"/rooms/{room.id}/status", json={"operational_status": "maintenance"})
    assert res.status_code == 200
    assert res.json()["status"] == "maintenance"
    [event] = audits(db, "room.status_changed")
    assert (event.actor_user_id, event.changes) == (receptionist.id, {"operational_status": ["available", "maintenance"]})


def test_status_of_an_occupied_room_cannot_change(db, client, tenant, admin, receptionist):
    room = make_room(db, tenant)
    make_stay(db, tenant, admin, room=room)
    login(db, client, receptionist)
    res = client.patch(f"/rooms/{room.id}/status", json={"operational_status": "cleaning"})
    assert res.status_code == 409
    assert res.json()["code"] == "room_occupied"
    assert db.get(Room, room.id).operational_status == "available"


def test_setting_the_same_status_writes_no_audit(db, client, tenant, receptionist):
    room = make_room(db, tenant)
    login(db, client, receptionist)
    assert client.patch(f"/rooms/{room.id}/status", json={"operational_status": "available"}).status_code == 200
    assert audits(db, "room.status_changed") == []


def test_occupied_cannot_be_set_by_hand(db, client, tenant, receptionist):
    room = make_room(db, tenant)
    login(db, client, receptionist)
    res = client.patch(f"/rooms/{room.id}/status", json={"operational_status": "occupied"})
    assert res.status_code == 422


def test_status_change_needs_permission(db, client, tenant, receptionist):
    from tests.factories import add_override
    room = make_room(db, tenant)
    add_override(db, receptionist, "room.status.update", "deny")
    login(db, client, receptionist)
    res = client.patch(f"/rooms/{room.id}/status", json={"operational_status": "cleaning"})
    assert res.status_code == 403
