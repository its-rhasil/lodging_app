"""Short stay -> full day conversion (M1 Day 3, task 3; DL-R10, DL-R23).

The fake clock starts at Mon 2026-11-16 08:00 UTC. Room: Full day 1200, Fresh-up 500 (2h, 60 min grace).
"""
import pytest

from app.models import FolioTransaction, Stay
from tests.factories import (
    add_override, daily_plan, log_in, make_plan, make_room, make_room_type, make_tenant, make_user,
)


@pytest.fixture
def tenant(db):
    return make_tenant(db)


@pytest.fixture
def freshup(db, tenant):
    return make_plan(db, tenant, name="Fresh-up", period_hours=2, grace_minutes=60)


@pytest.fixture
def room(db, tenant, freshup):
    room_type = make_room_type(db, tenant, capacity=2, daily_price="1200.00",
                               extra_rates={(freshup.id, 1): "500.00", (freshup.id, 2): "500.00"})
    return make_room(db, tenant, room_type=room_type)


@pytest.fixture
def receptionist(db, tenant):
    return make_user(db, tenant, role_code="receptionist")


def login(db, client, user):
    log_in(client, db, user)
    db.commit()


def check_in(db, client, room, plan):
    res = client.post("/stays", json={
        "room_id": room.id, "stay_plan_id": plan.id, "occupancy": 2,
        "guest": {"full_name": "Ravi Kumar", "phone": "9876543210"},
    })
    assert res.status_code == 201, res.json()
    return res.json()["id"]


def convert(client, stay_id, **body):
    return client.post(f"/stays/{stay_id}/convert-to-daily", json=body)


def test_conversion_reverses_blocks_and_posts_day_1(db, client, tenant, room, freshup, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id = check_in(db, client, room, freshup)
    fake_clock.advance(hours=5, minutes=30)  # blocks 1-3 due (block 3 at +5h)

    res = convert(client, stay_id)
    assert res.status_code == 200
    body = res.json()
    assert (body["stay_plan_name"], body["period_hours"], body["grace_minutes"]) == ("Full day", 24, 30)
    assert (body["listed_price"], body["agreed_price"]) == ("1200.00", "1200.00")
    assert body["folio"]["balance"] == "1200.00"

    stay = db.get(Stay, stay_id)
    assert stay.converted_from_plan_id == freshup.id
    rows = db.query(FolioTransaction).filter_by(folio_id=body["folio"]["id"]).order_by(FolioTransaction.id).all()
    blocks = [r for r in rows if r.txn_type == "room_charge" and r.posting_key.startswith(f"room:{freshup.id}:")]
    reversals = [r for r in rows if r.txn_type == "reversal"]
    assert len(blocks) == 3
    assert sorted(r.related_txn_id for r in reversals) == sorted(b.id for b in blocks)
    [day_1] = [r for r in rows if r.posting_key == f"room:{daily_plan(db, tenant).id}:1"]
    assert (day_1.amount, day_1.period_start_at) == (1200, stay.actual_check_in_at)


def test_clock_keeps_the_original_check_in(db, client, tenant, room, freshup, receptionist, fake_clock):
    login(db, client, receptionist)
    stay_id = check_in(db, client, room, freshup)
    fake_clock.advance(hours=3)
    convert(client, stay_id)

    fake_clock.advance(hours=21, minutes=29)  # 24h29 after check-in
    assert client.get(f"/stays/{stay_id}/folio").json()["balance"] == "1200.00"
    fake_clock.advance(minutes=1)             # 24h30 after check-in: day 2 due
    assert client.get(f"/stays/{stay_id}/folio").json()["balance"] == "2400.00"


def test_discount_at_conversion(db, client, tenant, room, freshup, receptionist):
    login(db, client, receptionist)
    stay_id = check_in(db, client, room, freshup)
    body = convert(client, stay_id, agreed_price="1000").json()
    assert (body["agreed_price"], body["discount_percent"], body["folio"]["balance"]) == ("1000.00", "16.67", "1000.00")


def test_discount_needs_the_override_permission(db, client, tenant, room, freshup, receptionist):
    add_override(db, receptionist, "stay.override_rate", "deny")
    login(db, client, receptionist)
    stay_id = check_in(db, client, room, freshup)
    assert convert(client, stay_id, agreed_price="1000").status_code == 403
    assert convert(client, stay_id).status_code == 200  # the listed price needs no extra permission


def test_waived_block_has_its_waiver_reversed_too(db, client, tenant, room, freshup, receptionist):
    login(db, client, receptionist)
    stay_id = check_in(db, client, room, freshup)
    folio = client.get(f"/stays/{stay_id}/folio").json()
    block_1 = [t for t in folio["transactions"] if t["txn_type"] == "room_charge"][0]["id"]
    client.post(f"/stays/{stay_id}/folio/transactions/{block_1}/waive", json={"amount": "200", "reason": "Regular"})

    body = convert(client, stay_id).json()
    assert body["folio"]["balance"] == "1200.00"  # not 1000: the waiver didn't survive the conversion


def test_full_day_stay_cannot_be_converted(db, client, tenant, room, receptionist):
    login(db, client, receptionist)
    stay_id = check_in(db, client, room, daily_plan(db, tenant))
    res = convert(client, stay_id)
    assert res.status_code == 422
    assert res.json()["code"] == "already_daily"


def test_conversion_needs_permission(db, client, tenant, room, freshup, receptionist):
    add_override(db, receptionist, "stay.convert_to_daily", "deny")
    login(db, client, receptionist)
    stay_id = check_in(db, client, room, freshup)
    assert convert(client, stay_id).status_code == 403
