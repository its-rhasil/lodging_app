"""Tenant isolation sweep (testing-strategy.md §7).

Every tenant route with an id in its path is called by tenant A's admin (who holds every
permission) with tenant B's real ids. Expect 404: never 403 (which would reveal that the
row exists) and never success. Routes come from app.main.ROUTERS: a new route with a path id
fails test_every_path_id_route_is_covered until it is added to PATH_IDS / BODIES below.
"""
import re
from datetime import datetime, timezone

import pytest
from fastapi.routing import APIRoute

from app.main import ROUTERS
from app.models import Folio, FolioTransaction
from app.service.posting_service import post_due_room_charges
from tests.factories import (
    daily_plan, log_in, make_room, make_room_type, make_stay, make_tenant, make_user,
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
