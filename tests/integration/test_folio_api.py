"""Folio API (M1 Day 2, task 5). The fake clock starts at Mon 2026-11-16 08:00 UTC.

Each test checks in through the API: full day, 1000/day, grace 30 min, period 1 posted.
"""
import uuid
from datetime import timedelta

import pytest

from app.models import AuditEvent, Folio, FolioTransaction, Stay
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
    db.commit()  # so a failing request's rollback can't undo the setup


def check_in(db, client, tenant):
    room = make_room(db, tenant, room_type=make_room_type(db, tenant, capacity=2, daily_price="1000.00"))
    db.commit()
    res = client.post("/stays", json={
        "room_id": room.id, "stay_plan_id": daily_plan(db, tenant).id, "occupancy": 1,
        "guest": {"full_name": "Ravi Kumar", "phone": "9876543210"},
    })
    assert res.status_code == 201
    return res.json()["id"]


@pytest.fixture
def stay_id(db, client, tenant, manager):
    """A stay checked in by a manager (who can do every folio operation)."""
    login(db, client, manager)
    return check_in(db, client, tenant)


def pay(client, stay_id, amount, key=None, method="cash"):
    return client.post(f"/stays/{stay_id}/folio/payments", json={
        "amount": amount, "method": method, "idempotency_key": str(key or uuid.uuid4()),
    })


def txn_id(folio, txn_type, n=0):
    return [t for t in folio["transactions"] if t["txn_type"] == txn_type][n]["id"]


def check_out_directly(db, stay_id, at):
    """Checkout is Day 3: mark the stay checked out in the DB for the pending-balance rules."""
    stay = db.get(Stay, stay_id)
    stay.status = "checked_out"
    stay.actual_checkout_at = at
    db.commit()


# --- posting -----------------------------------------------------------------

def test_opening_the_folio_posts_due_periods(db, client, stay_id, fake_clock):
    fake_clock.advance(hours=24, minutes=29)
    assert client.get(f"/stays/{stay_id}/folio").json()["balance"] == "1000.00"
    fake_clock.advance(minutes=1)  # Tue 08:30
    folio = client.get(f"/stays/{stay_id}/folio").json()
    assert folio["balance"] == "2000.00"
    assert [t["period_no"] for t in folio["transactions"]] == [1, 2]


def test_an_action_posts_due_periods_first(db, client, stay_id, fake_clock):
    fake_clock.advance(hours=24, minutes=20)          # folio opened at Tue 08:20: nothing due
    client.get(f"/stays/{stay_id}/folio")
    fake_clock.advance(minutes=20)                    # payment pressed at 08:40
    folio = pay(client, stay_id, "500").json()
    assert folio["balance"] == "1500.00"              # day 2 posted before the payment


# --- charges and payments -----------------------------------------------------

def test_charge_is_added_and_audited(db, client, stay_id, manager):
    res = client.post(f"/stays/{stay_id}/folio/charges", json={"amount": "250", "description": "Dinner"})
    assert res.status_code == 201
    assert res.json()["balance"] == "1250.00"
    [event] = db.query(AuditEvent).filter_by(action="folio.charge_posted").all()
    assert event.actor_user_id == manager.id


def test_double_submitted_payment_records_once(db, client, stay_id):
    key = uuid.uuid4()
    first = pay(client, stay_id, "600", key)
    second = pay(client, stay_id, "600", key)
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["balance"] == "400.00"
    assert db.query(FolioTransaction).filter_by(txn_type="payment").count() == 1


def test_reused_payment_key_with_a_different_amount_is_rejected(db, client, stay_id):
    key = uuid.uuid4()
    pay(client, stay_id, "600", key)
    res = pay(client, stay_id, "700", key)
    assert res.status_code == 409
    assert res.json()["code"] == "idempotency_key_reused"


def test_overpayment_is_allowed_while_staying(db, client, stay_id):
    assert pay(client, stay_id, "1500").json()["balance"] == "-500.00"


# --- refunds -----------------------------------------------------------------

def test_refund_is_limited_to_the_credit(db, client, stay_id):
    pay(client, stay_id, "1500")  # guest is 500 in credit
    too_much = client.post(f"/stays/{stay_id}/folio/refunds",
                           json={"amount": "600", "method": "cash", "reason": "Overpaid"})
    assert too_much.json()["code"] == "refund_exceeds_credit"
    ok = client.post(f"/stays/{stay_id}/folio/refunds",
                     json={"amount": "500", "method": "cash", "reason": "Overpaid"})
    assert ok.status_code == 201
    assert ok.json()["balance"] == "0.00"


def test_receptionist_cannot_refund(db, client, tenant, receptionist):
    login(db, client, receptionist)
    stay = check_in(db, client, tenant)
    res = client.post(f"/stays/{stay}/folio/refunds", json={"amount": "1", "method": "cash", "reason": "x"})
    assert res.status_code == 403


# --- waivers -----------------------------------------------------------------

def test_waivers_are_limited_cumulatively(db, client, stay_id):
    folio = client.get(f"/stays/{stay_id}/folio").json()
    day_1 = txn_id(folio, "room_charge")
    first = client.post(f"/stays/{stay_id}/folio/transactions/{day_1}/waive",
                        json={"amount": "300", "reason": "Late arrival"})
    assert first.json()["balance"] == "700.00"
    charge_row = [t for t in first.json()["transactions"] if t["id"] == day_1][0]
    assert charge_row["waivable_amount"] == "700.00"

    second = client.post(f"/stays/{stay_id}/folio/transactions/{day_1}/waive",
                         json={"amount": "800", "reason": "More"})
    assert second.status_code == 422
    assert second.json()["code"] == "waiver_exceeds_remaining"


def test_payments_cannot_be_waived(db, client, stay_id):
    folio = pay(client, stay_id, "100").json()
    res = client.post(f"/stays/{stay_id}/folio/transactions/{txn_id(folio, 'payment')}/waive",
                      json={"amount": "50", "reason": "x"})
    assert res.json()["code"] == "not_waivable"


# --- reversals ---------------------------------------------------------------

def test_reversal_is_opposite_and_only_once(db, client, stay_id):
    folio = client.post(f"/stays/{stay_id}/folio/charges", json={"amount": "250", "description": "Dinner"}).json()
    dinner = txn_id(folio, "charge")
    res = client.post(f"/stays/{stay_id}/folio/transactions/{dinner}/reverse", json={"reason": "Wrong room"})
    assert res.status_code == 201
    body = res.json()
    reversal = [t for t in body["transactions"] if t["txn_type"] == "reversal"][0]
    assert (reversal["direction"], reversal["amount"], reversal["related_txn_id"]) == ("credit", "250.00", dinner)
    assert body["balance"] == "1000.00"

    again = client.post(f"/stays/{stay_id}/folio/transactions/{dinner}/reverse", json={"reason": "x"})
    assert again.json()["code"] == "already_reversed"
    of_reversal = client.post(f"/stays/{stay_id}/folio/transactions/{reversal['id']}/reverse",
                              json={"reason": "x"})
    assert of_reversal.json()["code"] == "cannot_reverse_reversal"


def test_reversed_charge_cannot_be_waived(db, client, stay_id):
    folio = client.post(f"/stays/{stay_id}/folio/charges", json={"amount": "250", "description": "Dinner"}).json()
    dinner = txn_id(folio, "charge")
    client.post(f"/stays/{stay_id}/folio/transactions/{dinner}/reverse", json={"reason": "Wrong room"})
    res = client.post(f"/stays/{stay_id}/folio/transactions/{dinner}/waive", json={"amount": "10", "reason": "x"})
    assert res.json()["code"] == "already_reversed"


def test_reverse_waivers_first(db, client, stay_id):
    folio = client.get(f"/stays/{stay_id}/folio").json()
    day_1 = txn_id(folio, "room_charge")
    folio = client.post(f"/stays/{stay_id}/folio/transactions/{day_1}/waive",
                        json={"amount": "300", "reason": "Late arrival"}).json()
    waiver = txn_id(folio, "waiver")

    blocked = client.post(f"/stays/{stay_id}/folio/transactions/{day_1}/reverse", json={"reason": "x"})
    assert blocked.status_code == 409
    assert blocked.json()["details"]["waiver_ids"] == [waiver]

    client.post(f"/stays/{stay_id}/folio/transactions/{waiver}/reverse", json={"reason": "Undo waiver"})
    done = client.post(f"/stays/{stay_id}/folio/transactions/{day_1}/reverse", json={"reason": "Never stayed"})
    assert done.status_code == 201
    assert done.json()["balance"] == "0.00"


def test_receptionist_cannot_reverse(db, client, tenant, receptionist):
    login(db, client, receptionist)
    stay = check_in(db, client, tenant)
    folio = client.get(f"/stays/{stay}/folio").json()
    res = client.post(f"/stays/{stay}/folio/transactions/{txn_id(folio, 'room_charge')}/reverse",
                      json={"reason": "x"})
    assert res.status_code == 403


# --- after checkout (pending balance) -----------------------------------------

def test_pending_balance_rules_and_auto_close(db, client, stay_id, fake_clock):
    check_out_directly(db, stay_id, fake_clock.now() + timedelta(hours=2))  # owes 1000

    charge = client.post(f"/stays/{stay_id}/folio/charges", json={"amount": "50", "description": "x"})
    assert charge.json()["code"] == "stay_not_active"
    refund = client.post(f"/stays/{stay_id}/folio/refunds", json={"amount": "1", "method": "cash", "reason": "x"})
    assert refund.json()["code"] == "stay_not_active"
    too_much = pay(client, stay_id, "1200")
    assert too_much.json()["code"] == "amount_exceeds_balance"

    pay(client, stay_id, "600")
    settled = pay(client, stay_id, "400").json()
    assert (settled["balance"], settled["status"]) == ("0.00", "closed")
    assert db.get(Folio, settled["id"]).closed_by_user_id is None

    after = pay(client, stay_id, "1")
    assert after.json()["code"] == "folio_closed"


def test_waiver_can_settle_a_pending_balance(db, client, stay_id, fake_clock):
    check_out_directly(db, stay_id, fake_clock.now() + timedelta(hours=2))
    folio = client.get(f"/stays/{stay_id}/folio").json()
    res = client.post(f"/stays/{stay_id}/folio/transactions/{txn_id(folio, 'room_charge')}/waive",
                      json={"amount": "1000", "reason": "Written off by manager"})
    assert (res.json()["balance"], res.json()["status"]) == ("0.00", "closed")


# --- isolation and actors ----------------------------------------------------------

def test_another_tenants_stay_is_not_found(db, client, stay_id):
    other = make_tenant(db)
    login(db, client, make_user(db, other, role_code="manager"))
    assert client.get(f"/stays/{stay_id}/folio").status_code == 404
    assert pay(client, stay_id, "10").status_code == 404


def test_transaction_of_another_folio_is_not_found(db, client, tenant, stay_id):
    other_stay = check_in(db, client, tenant)
    other_folio = client.get(f"/stays/{other_stay}/folio").json()
    res = client.post(f"/stays/{stay_id}/folio/transactions/{txn_id(other_folio, 'room_charge')}/waive",
                      json={"amount": "10", "reason": "x"})
    assert res.status_code == 404


def test_every_money_row_has_an_actor_or_the_system_marker(db, client, stay_id, manager, fake_clock):
    fake_clock.advance(hours=25)
    pay(client, stay_id, "500")
    client.post(f"/stays/{stay_id}/folio/charges", json={"amount": "250", "description": "Dinner"})
    for txn in db.query(FolioTransaction).all():
        expected = None if txn.txn_type == "room_charge" else manager.id
        assert txn.created_by_user_id == expected
