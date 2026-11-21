"""Tenant isolation sweep (testing-strategy.md §7).

1. Routes with an id in the path: tenant A's admin (who holds every permission) calls each one
   with tenant B's real ids. Expect 404: never 403 (which would reveal that the row exists) and
   never success.
2. Routes without a path id (lists, creates, settings): tenant B's rows carry a marker ("zzb");
   no list tenant A can read may contain it. Tenant B reading the same lists must see it
   (positive control: proves the marker data exists, so "A doesn't see it" means something).
3. Ids inside request bodies (change-room, room type of a room, plans in rates, B's transaction
   on A's own stay): 404.

Routes come from app.main.ROUTERS: a new route fails test_every_path_id_route_is_covered or
test_every_route_without_a_path_id_is_covered until it is added below.
"""
import re
from datetime import datetime, timezone

import pytest
from fastapi.routing import APIRoute

from app.main import ROUTERS
from app.models import AuditEvent, Folio, FolioTransaction, Guest, TenantSettings
from app.service.posting_service import post_due_room_charges
from tests.factories import (
    daily_plan, log_in, make_plan, make_room, make_room_type, make_stay, make_tenant, make_user,
)

# Path parameter -> which of tenant B's rows to use.
PATH_IDS = {
    "plan_id": "plan", "room_type_id": "room_type", "room_id": "room", "user_id": "user",
    "stay_id": "stay", "txn_id": "txn",
}
# A valid body for routes that need one, so the request reaches the lookup (and its 404).
BODIES = {
    ("PATCH", "/stay-plans/{plan_id}"): {"grace_minutes": 5},
    ("PATCH", "/room-types/{room_type_id}"): {"name": "Renamed"},
    ("PATCH", "/rooms/{room_id}"): {"room_number": "X1"},
    ("PATCH", "/rooms/{room_id}/status"): {"operational_status": "cleaning"},
    ("PUT", "/users/{user_id}/overrides"): {"overrides": []},
    ("PATCH", "/stays/{stay_id}/extend"): {"expected_checkout_at": "2026-12-01T10:00:00+00:00"},
    ("POST", "/stays/{stay_id}/change-room"): {"new_room_id": "A_ROOM"},
    ("POST", "/stays/{stay_id}/correct-price"): {"agreed_price": "10", "reason": "x"},
    ("POST", "/stays/{stay_id}/cancel"): {"reason": "x"},
    ("POST", "/stays/{stay_id}/folio/charges"): {"amount": "10", "description": "x"},
    ("POST", "/stays/{stay_id}/folio/payments"): {
        "amount": "10", "method": "cash", "idempotency_key": "6f1c2a52-2f0e-4c1a-9a3e-2b7b0c1d9e11"},
    ("POST", "/stays/{stay_id}/folio/refunds"): {"amount": "10", "method": "cash", "reason": "x"},
    ("POST", "/stays/{stay_id}/folio/transactions/{txn_id}/waive"): {"amount": "10", "reason": "x"},
    ("POST", "/stays/{stay_id}/folio/transactions/{txn_id}/reverse"): {"reason": "x"},
}
QUERY = {("GET", "/rooms/{room_id}/offers"): {"occupancy": 1}}


def _path_id_routes():
    for router in ROUTERS:
        for route in router.routes:
            if isinstance(route, APIRoute) and "{" in route.path and not route.path.startswith("/platform"):
                for method in route.methods:
                    yield method, route.path


ROUTES = sorted(_path_id_routes())


def test_every_path_id_route_is_covered():
    assert len(ROUTES) > 15
    for method, path in ROUTES:
        for name in re.findall(r"\{([^}]+)\}", path):
            assert name in PATH_IDS, f"{method} {path}: add {name!r} to PATH_IDS"


@pytest.fixture
def tenant_b(db):
    tenant = make_tenant(db)
    user = make_user(db, tenant, role_code="manager")
    room_type = make_room_type(db, tenant)
    stay = make_stay(db, tenant, user, room=make_room(db, tenant, room_type=room_type))
    folio = db.query(Folio).filter_by(stay_id=stay.id).one()
    post_due_room_charges(db, folio, stay, datetime(2026, 11, 1, 12, tzinfo=timezone.utc))
    txn = db.query(FolioTransaction).filter_by(folio_id=folio.id).first()
    return {"plan": daily_plan(db, tenant), "room_type": room_type, "room": make_room(db, tenant, room_type=room_type),
            "user": user, "stay": stay, "txn": txn}


@pytest.mark.parametrize("method,path", ROUTES, ids=lambda v: str(v))
def test_tenant_a_gets_404_for_tenant_b_ids(db, client, tenant_b, method, path):
    tenant_a = make_tenant(db)
    a_room = make_room(db, tenant_a)
    log_in(client, db, make_user(db, tenant_a, role_code="tenant_admin"))
    db.commit()

    url = re.sub(r"\{([^}]+)\}", lambda m: str(tenant_b[PATH_IDS[m.group(1)]].id), path)
    body = dict(BODIES.get((method, path), {}))
    if body.get("new_room_id") == "A_ROOM":
        body["new_room_id"] = a_room.id
    res = client.request(method, url, json=body or None, params=QUERY.get((method, path)))
    assert res.status_code == 404, f"{method} {url}: {res.status_code} {res.json()}"


@pytest.mark.parametrize("field", ["room_id", "stay_plan_id", "guest_id"])
def test_check_in_with_tenant_b_ids_in_the_body_is_404(db, client, tenant_b, field):
    tenant_a = make_tenant(db)
    room = make_room(db, tenant_a)
    log_in(client, db, make_user(db, tenant_a, role_code="tenant_admin"))
    db.commit()
    body = {"room_id": room.id, "stay_plan_id": daily_plan(db, tenant_a).id, "occupancy": 1,
            "guest": {"full_name": "A", "phone": "9876543210"}}
    if field == "room_id":
        body["room_id"] = tenant_b["room"].id
    elif field == "stay_plan_id":
        body["stay_plan_id"] = tenant_b["plan"].id
    else:
        body["guest_id"] = tenant_b["stay"].guest_id
        del body["guest"]
    res = client.post("/stays", json=body)
    assert res.status_code == 404, res.json()


# --- 2. Routes without a path id: lists must never show tenant B's rows ------------------

MARKER = "zzb"          # in every name, number, email and summary of tenant B (checked lowercase)
B_TIMEZONE = "Pacific/Fiji"
B_PHONE = "+919812300077"

# (path, query, tenant B must see the marker in its own response)
LIST_REQUESTS = [
    ("/audit", None, True),
    ("/auth/me", None, True),
    ("/dashboard", None, True),
    ("/guests", {"phone": "98123 00077"}, True),
    ("/guests", {"q": "zzb"}, True),
    ("/room-types", None, True),
    ("/rooms", None, True),
    ("/settings", None, False),            # checked with B_TIMEZONE instead
    ("/stay-plans", None, True),
    ("/stays", None, True),
    ("/stays", {"status": "checked_out"}, True),
    ("/stays/pending-balances", None, True),
    ("/users", None, True),
    ("/users/permission-catalogue", None, False),  # the same global catalogue for everyone
]
# Writes without a path id, and where their tenant safety is tested.
WRITES_WITHOUT_PATH_ID = {
    ("POST", "/auth/login"): "finds the user by email; the session carries that user's tenant",
    ("POST", "/auth/logout"): "ends the caller's own session only",
    ("POST", "/stays"): "test_check_in_with_tenant_b_ids_in_the_body_is_404",
    ("POST", "/rooms"): "test_ids_in_the_body_from_tenant_b_are_404[room_create]",
    ("POST", "/room-types"): "test_ids_in_the_body_from_tenant_b_are_404[room_type_create]",
    ("POST", "/stay-plans"): "no ids in the body; the tenant comes from the session",
    ("POST", "/users"): "no ids in the body; the tenant comes from the session",
    ("PATCH", "/settings"): "test_settings_update_changes_only_the_callers_tenant",
}


def _routes_without_path_id():
    for router in ROUTERS:
        for route in router.routes:
            if isinstance(route, APIRoute) and "{" not in route.path and not route.path.startswith("/platform"):
                for method in route.methods:
                    yield method, route.path


def test_every_route_without_a_path_id_is_covered():
    listed = {path for path, _, _ in LIST_REQUESTS}
    missing = []
    for method, path in _routes_without_path_id():
        if method == "GET" and path in listed:
            continue
        if (method, path) in WRITES_WITHOUT_PATH_ID:
            continue
        missing.append(f"{method} {path}")
    assert missing == [], f"add to LIST_REQUESTS or WRITES_WITHOUT_PATH_ID: {missing}"


@pytest.fixture
def marked_b(db):
    """Tenant B with a marker on everything a list could show, and its admin."""
    tenant = make_tenant(db, name="ZZB Lodge")
    db.query(TenantSettings).filter_by(tenant_id=tenant.id).one().timezone = B_TIMEZONE
    admin = make_user(db, tenant, role_code="tenant_admin", email="zzb-admin@example.com")
    admin.name = "ZZB Admin"
    make_plan(db, tenant, name="ZZB Plan")
    room_type = make_room_type(db, tenant)
    room_type.name = "ZZB Type"
    # An active stay (room grid, active stays, guest lookup by phone and name).
    active = make_stay(db, tenant, admin, room=make_room(db, tenant, room_type=room_type, number="ZZB-1"))
    guest = db.get(Guest, active.guest_id)
    guest.full_name, guest.phone = "ZZB Guest", B_PHONE
    # A checked-out stay that still owes money (pending balances, checked-out list).
    left = make_stay(db, tenant, admin, room=make_room(db, tenant, room_type=room_type, number="ZZB-2"))
    db.get(Guest, left.guest_id).full_name = "ZZB Debtor"
    folio = db.query(Folio).filter_by(stay_id=left.id).one()
    post_due_room_charges(db, folio, left, datetime(2026, 11, 1, 13, tzinfo=timezone.utc))
    left.status, left.actual_checkout_at = "checked_out", datetime(2026, 11, 2, 10, tzinfo=timezone.utc)
    db.add(AuditEvent(tenant_id=tenant.id, actor_type="tenant_user", actor_user_id=admin.id,
                      action="room.created", entity_type="room", entity_id="1", summary="ZZB audit row"))
    db.flush()
    return admin


@pytest.fixture
def admin_a(db):
    tenant = make_tenant(db, name="Alpha Lodge")
    make_room(db, tenant, number="A-1")
    return make_user(db, tenant, role_code="tenant_admin")


@pytest.mark.parametrize("path,query,b_sees_marker", LIST_REQUESTS, ids=lambda v: str(v))
def test_lists_never_show_another_tenants_rows(db, client, fake_clock, marked_b, admin_a, path, query, b_sees_marker):
    # Positive control: tenant B sees its own marked rows.
    log_in(client, db, marked_b)
    db.commit()
    own = client.get(path, params=query)
    assert own.status_code == 200, own.json()
    if b_sees_marker:
        assert MARKER in own.text.lower(), f"{path}: test data not visible to its own tenant"

    # Tenant A must see none of them.
    log_in(client, db, admin_a)
    db.commit()
    res = client.get(path, params=query)
    assert res.status_code == 200, res.json()
    assert MARKER not in res.text.lower(), f"{path} leaked tenant B's data: {res.text[:300]}"
    assert B_TIMEZONE not in res.text


def test_settings_update_changes_only_the_callers_tenant(db, client, marked_b, admin_a):
    log_in(client, db, admin_a)
    db.commit()
    res = client.patch("/settings", json={"timezone": "Asia/Dubai"})
    assert res.status_code == 200, res.json()
    b_settings = db.query(TenantSettings).filter_by(tenant_id=marked_b.tenant_id).one()
    db.refresh(b_settings)
    assert b_settings.timezone == B_TIMEZONE


# --- 3. Ids inside request bodies ---------------------------------------------------------

BODY_ID_CASES = ["change_room", "room_create", "room_update", "room_type_create", "room_type_update",
                 "reverse_b_txn", "waive_b_txn"]


@pytest.mark.parametrize("ids_from", ["tenant_b", "own"])
@pytest.mark.parametrize("case", BODY_ID_CASES)
def test_ids_in_the_body_from_tenant_b_are_404(db, client, fake_clock, tenant_b, case, ids_from):
    """ids_from="own" is the control: the same request with tenant A's own ids must succeed,
    so the 404 for tenant B's ids can only come from the tenant check."""
    tenant_a = make_tenant(db)
    admin = make_user(db, tenant_a, role_code="tenant_admin")
    a_type = make_room_type(db, tenant_a)
    a_free_room = make_room(db, tenant_a, room_type=a_type)
    a_other_type = make_room_type(db, tenant_a)
    a_extra_plan = make_plan(db, tenant_a)
    a_stay = make_stay(db, tenant_a, admin, room=make_room(db, tenant_a, room_type=a_type))
    a_folio = db.query(Folio).filter_by(stay_id=a_stay.id).one()
    post_due_room_charges(db, a_folio, a_stay, datetime(2026, 11, 1, 13, tzinfo=timezone.utc))
    a_txn = db.query(FolioTransaction).filter_by(folio_id=a_folio.id).first()
    log_in(client, db, admin)
    db.commit()

    if ids_from == "tenant_b":
        room_id, type_id, plan_id, txn_id = (tenant_b["room"].id, tenant_b["room_type"].id,
                                             tenant_b["plan"].id, tenant_b["txn"].id)
    else:
        room_id, type_id, plan_id, txn_id = a_free_room.id, a_other_type.id, a_extra_plan.id, a_txn.id
    a_daily = daily_plan(db, tenant_a).id
    rates = [{"stay_plan_id": a_daily, "occupancy": occ, "price": "1000"} for occ in (1, 2)]
    rates.append({"stay_plan_id": plan_id, "occupancy": 1, "price": "500"})
    requests = {
        "change_room": ("POST", f"/stays/{a_stay.id}/change-room", {"new_room_id": room_id}),
        "room_create": ("POST", "/rooms", {"room_type_id": type_id, "room_number": "A-99"}),
        "room_update": ("PATCH", f"/rooms/{a_free_room.id}", {"room_type_id": type_id}),
        "room_type_create": ("POST", "/room-types", {"name": "A New Type", "capacity": 2, "rates": rates}),
        "room_type_update": ("PATCH", f"/room-types/{a_type.id}", {"rates": rates}),
        "reverse_b_txn": ("POST", f"/stays/{a_stay.id}/folio/transactions/{txn_id}/reverse", {"reason": "x"}),
        "waive_b_txn": ("POST", f"/stays/{a_stay.id}/folio/transactions/{txn_id}/waive",
                        {"amount": "10", "reason": "x"}),
    }
    method, url, body = requests[case]
    res = client.request(method, url, json=body)
    if ids_from == "tenant_b":
        assert res.status_code == 404, f"{case}: {res.status_code} {res.json()}"
    else:
        assert res.status_code < 400, f"control {case}: {res.status_code} {res.json()}"
