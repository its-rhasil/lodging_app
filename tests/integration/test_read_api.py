"""Read APIs (M1 Day 3, task 4): dashboard, stay lists, pending balances, stay detail,
guest search, audit list, tenant settings. The fake clock starts at Mon 2026-11-16 08:00 UTC."""
import uuid
from datetime import timedelta

import pytest

from app.models import AuditEvent
from tests.factories import (
    daily_plan, log_in, make_guest, make_room, make_room_type, make_tenant, make_user,
)


@pytest.fixture
def tenant(db):
    return make_tenant(db)


@pytest.fixture
def room_type(db, tenant):
    return make_room_type(db, tenant, capacity=2, daily_price="1000.00")


@pytest.fixture
def receptionist(db, tenant):
    return make_user(db, tenant, role_code="receptionist")


@pytest.fixture
def manager(db, tenant):
    return make_user(db, tenant, role_code="manager")


@pytest.fixture
def admin(db, tenant):
    return make_user(db, tenant, role_code="tenant_admin")


def login(db, client, user):
    log_in(client, db, user)
    db.commit()


def check_in(db, client, tenant, room, name="Ravi Kumar", phone="9876543210"):
    res = client.post("/stays", json={
        "room_id": room.id, "stay_plan_id": daily_plan(db, tenant).id, "occupancy": 1,
        "guest": {"full_name": name, "phone": phone},
    })
    assert res.status_code == 201, res.json()
    return res.json()["id"]


def pay(client, stay_id, amount):
    client.post(f"/stays/{stay_id}/folio/payments",
                json={"amount": amount, "method": "cash", "idempotency_key": str(uuid.uuid4())})


# --- dashboard -----------------------------------------------------------------

def test_dashboard_shows_rooms_guests_and_balances(db, client, tenant, room_type, receptionist, fake_clock):
    r101 = make_room(db, tenant, room_type=room_type, number="101")
    r102 = make_room(db, tenant, room_type=room_type, number="102")
    r103 = make_room(db, tenant, room_type=room_type, number="103")
    r103.operational_status = "maintenance"
    hidden = make_room(db, tenant, room_type=room_type, number="999")
    hidden.is_active = False
    login(db, client, receptionist)
    check_in(db, client, tenant, r101)

    fake_clock.advance(hours=24, minutes=31)  # day 2 due: loading the grid posts it
    res = client.get("/dashboard")
    assert res.status_code == 200
    body = res.json()
    assert body["summary"] == {
        "total_rooms": 3, "available": 1, "occupied": 1, "cleaning": 0, "maintenance": 1,
        "pending_balances_count": 0, "pending_balances_total": "0.00",
    }
    cards = {c["room_number"]: c for c in body["rooms"]}
    assert set(cards) == {"101", "102", "103"}
    assert cards["101"]["status"] == "occupied"
    assert (cards["101"]["stay"]["guest_name"], cards["101"]["stay"]["balance"]) == ("Ravi Kumar", "2000.00")
    # Checked in Mon 08:00, now Tue 08:31 (2 periods due) -> next charge Wed 08:30.
    from datetime import datetime
    next_charge = datetime.fromisoformat(cards["101"]["stay"]["next_charge_at"])
    assert next_charge == fake_clock.now().replace(hour=8, minute=30) + timedelta(days=1)
    assert cards["102"]["stay"] is None
    assert r102.id == cards["102"]["room_id"]


def test_dashboard_counts_pending_balances(db, client, tenant, room_type, manager):
    room = make_room(db, tenant, room_type=room_type)
    login(db, client, manager)
    stay_id = check_in(db, client, tenant, room)
    pay(client, stay_id, "400")
    client.post(f"/stays/{stay_id}/checkout", json={"force_reason": "Pays tomorrow"})
    summary = client.get("/dashboard").json()["summary"]
    assert (summary["pending_balances_count"], summary["pending_balances_total"]) == (1, "600.00")
    assert summary["cleaning"] == 1


def test_one_stay_with_a_wrong_check_in_time_does_not_break_the_grid(db, client, tenant, room_type, receptionist,
                                                                     manager, fake_clock):
    from tests.factories import make_stay
    good_room = make_room(db, tenant, room_type=room_type, number="101")
    bad_room = make_room(db, tenant, room_type=room_type, number="102")
    bad = make_stay(db, tenant, manager, room=bad_room, check_in_at=fake_clock.now().replace(year=26))
    login(db, client, receptionist)
    check_in(db, client, tenant, good_room)

    res = client.get("/dashboard")
    assert res.status_code == 200
    assert {c["room_number"]: c["status"] for c in res.json()["rooms"]} == {"101": "occupied", "102": "occupied"}
    opened = client.get(f"/stays/{bad.id}")
    assert opened.status_code == 409
    assert opened.json()["code"] == "too_many_periods"


# --- stay lists and detail ----------------------------------------------------------

def test_active_stays_list_posts_and_shows_balances(db, client, tenant, room_type, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, make_room(db, tenant, room_type=room_type, number="101"))
    fake_clock.advance(hours=25)
    [row] = client.get("/stays").json()
    assert (row["id"], row["room_number"], row["balance"], row["stay_plan_name"]) == (stay_id, "101", "2000.00",
                                                                                      "Full day")


def test_pending_balances_list(db, client, tenant, room_type, manager):
    login(db, client, manager)
    owing = check_in(db, client, tenant, make_room(db, tenant, room_type=room_type))
    settled = check_in(db, client, tenant, make_room(db, tenant, room_type=room_type), phone="9000000001")
    client.post(f"/stays/{owing}/checkout", json={"force_reason": "Pays tomorrow"})
    pay(client, settled, "1000")
    client.post(f"/stays/{settled}/checkout")

    rows = client.get("/stays/pending-balances").json()
    assert [(r["id"], r["balance"], r["forced_checkout_reason"]) for r in rows] == [
        (owing, "1000.00", "Pays tomorrow")]
    checked_out = {r["id"] for r in client.get("/stays", params={"status": "checked_out"}).json()}
    assert checked_out == {owing, settled}


def test_stay_detail_includes_the_folio_and_posts(db, client, tenant, room_type, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, make_room(db, tenant, room_type=room_type))
    fake_clock.advance(hours=24, minutes=30)
    body = client.get(f"/stays/{stay_id}").json()
    assert body["folio"]["balance"] == "2000.00"
    assert [t["period_no"] for t in body["folio"]["transactions"]] == [1, 2]


def test_stay_lists_are_tenant_scoped(db, client, tenant, room_type, receptionist):
    login(db, client, receptionist)
    stay_id = check_in(db, client, tenant, make_room(db, tenant, room_type=room_type))
    login(db, client, make_user(db, make_tenant(db), role_code="manager"))
    assert client.get("/stays").json() == []
    assert client.get(f"/stays/{stay_id}").status_code == 404


# --- guest search ----------------------------------------------------------------

def test_guest_search_by_name_or_partial_phone(db, client, tenant, receptionist):
    ravi = make_guest(db, tenant, phone="+919876543210")
    ravi.full_name = "Ravi Kumar"
    other = make_guest(db, tenant, phone="+919111111111")
    other.full_name = "Priya Nair"
    make_guest(db, make_tenant(db), phone="+919876543210")  # another lodge's guest
    login(db, client, receptionist)

    assert [g["id"] for g in client.get("/guests", params={"q": "ravi"}).json()] == [ravi.id]
    assert [g["id"] for g in client.get("/guests", params={"q": "43210"}).json()] == [ravi.id]
    assert client.get("/guests", params={"q": "r"}).json()["code"] == "search_too_short"
    assert client.get("/guests").json()["code"] == "invalid_query"


# --- audit list ------------------------------------------------------------------

def test_audit_list_is_for_permitted_users_and_filters(db, client, tenant, room_type, receptionist, admin):
    login(db, client, receptionist)
    check_in(db, client, tenant, make_room(db, tenant, room_type=room_type))
    assert client.get("/audit").status_code == 403

    login(db, client, admin)
    rows = client.get("/audit", params={"action": "stay.checked_in"}).json()
    assert [(r["action"], r["actor_user_id"], r["actor_name"]) for r in rows] == [
        ("stay.checked_in", receptionist.id, receptionist.name)]


def test_audit_shows_names_to_anyone_with_audit_view(db, client, tenant, room_type, receptionist, manager):
    from tests.factories import add_override
    add_override(db, manager, "audit.view", "grant")  # a manager who may see the audit but not list users
    login(db, client, receptionist)
    check_in(db, client, tenant, make_room(db, tenant, room_type=room_type))

    login(db, client, manager)
    assert client.get("/users").status_code == 403
    [row] = client.get("/audit", params={"action": "stay.checked_in"}).json()
    assert row["actor_name"] == receptionist.name


def test_audit_list_is_tenant_scoped(db, client, tenant, admin):
    other = make_tenant(db)
    db.add(AuditEvent(tenant_id=other.id, actor_type="system", action="secret.thing"))
    login(db, client, admin)
    assert all(r["action"] != "secret.thing" for r in client.get("/audit").json())


# --- tenant settings ----------------------------------------------------------------

def test_everyone_reads_settings_but_only_admin_changes_them(db, client, tenant, receptionist, admin):
    login(db, client, receptionist)
    assert client.get("/settings").json()["timezone"] == "Asia/Kolkata"
    assert client.patch("/settings", json={"currency": "usd"}).status_code == 403

    login(db, client, admin)
    res = client.patch("/settings", json={"currency": "usd", "max_backdate_minutes": 60})
    assert res.status_code == 200
    assert (res.json()["currency"], res.json()["max_backdate_minutes"]) == ("USD", 60)
    assert db.query(AuditEvent).filter_by(action="settings.updated").count() == 1


def test_unknown_timezone_is_rejected(db, client, tenant, admin):
    login(db, client, admin)
    assert client.patch("/settings", json={"timezone": "Europe/London"}).status_code == 200
    res = client.patch("/settings", json={"timezone": "Mars/Olympus"})
    assert res.json()["code"] == "unknown_timezone"
