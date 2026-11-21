"""Concurrency smoke tests (testing-strategy.md §10). Run with: pytest -m concurrency

Each race starts two threads together (threading.Barrier), each with its own DB connection,
calling the services directly with real commits. Afterwards the test schema is rebuilt:
folio_transactions and audit_events are append-only, so they can't be truncated.
"""
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.permissions import ROLE_PERMISSIONS
from app.core.principal import Principal
from app.core.request_context import RequestMeta
from app.database import Base
from app.models import FolioTransaction, Stay
from app.service import folio_service, room_service, stay_service
from tests.conftest import _seed_rbac
from tests.factories import daily_plan, make_room, make_tenant, make_user

pytestmark = pytest.mark.concurrency

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)
META = RequestMeta()


@pytest.fixture
def engine_committed(engine):
    yield engine
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        _seed_rbac(conn)


@pytest.fixture
def world(engine_committed):
    """A committed tenant with a manager, a room and the daily plan."""
    with Session(engine_committed) as db:
        tenant = make_tenant(db)
        user = make_user(db, tenant, role_code="manager")
        room = make_room(db, tenant)
        plan = daily_plan(db, tenant)
        db.commit()
        principal = Principal(kind="tenant", user_id=user.id, tenant_id=tenant.id, role_code="manager",
                              permissions=ROLE_PERMISSIONS["manager"], session_id=0)
        return {"engine": engine_committed, "principal": principal, "room_id": room.id, "plan_id": plan.id}


def race(engine, *calls):
    """Run each call(db) in its own thread and session, started together. Returns results/errors."""
    barrier = threading.Barrier(len(calls))
    results = [None] * len(calls)

    def run(i, call):
        with Session(engine) as db:
            barrier.wait()
            try:
                results[i] = ("ok", call(db))
            except DomainError as exc:
                db.rollback()
                results[i] = ("error", exc.code)

    threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def check_in(world, phone="9876543210"):
    def call(db):
        return stay_service.check_in(
            db, world["principal"], room_id=world["room_id"], stay_plan_id=world["plan_id"], occupancy=1,
            guest_id=None, guest={"full_name": "Guest", "phone": phone}, agreed_price=None, rate_reason=None,
            check_in_at=None, backdate_reason=None, expected_checkout_at=None, now=NOW, meta=META,
        )
    return call


def test_two_check_ins_into_the_same_room(world):
    results = race(world["engine"], check_in(world, "9000000001"), check_in(world, "9000000002"))
    assert sorted(kind for kind, _ in results) == ["error", "ok"]
    assert [value for kind, value in results if kind == "error"] == ["room_occupied"]
    with Session(world["engine"]) as db:
        assert db.query(Stay).filter_by(room_id=world["room_id"], status="active").count() == 1


def test_status_change_against_a_check_in(world):
    def set_maintenance(db):
        return room_service.set_status(db, world["principal"], world["room_id"], "maintenance", meta=META)

    results = race(world["engine"], check_in(world), set_maintenance)
    outcomes = sorted(kind for kind, _ in results)
    assert outcomes == ["error", "ok"]  # never both
    with Session(world["engine"]) as db:
        active = db.query(Stay).filter_by(room_id=world["room_id"], status="active").count()
        room = room_service.get_room(db, world["principal"].tenant_id, world["room_id"])
        assert (active, room.operational_status) in {(1, "available"), (0, "maintenance")}


def test_same_payment_twice_in_parallel_records_once(world):
    with Session(world["engine"]) as db:
        stay_id = check_in(world)(db)["id"]
    key = uuid.uuid4()

    def pay(db):
        return folio_service.record_payment(db, world["principal"], stay_id, amount=Decimal("500"),
                                            method="cash", reference=None, idempotency_key=key,
                                            now=NOW, meta=META)

    results = race(world["engine"], pay, pay)
    assert all(kind == "ok" for kind, _ in results)
    with Session(world["engine"]) as db:
        assert db.query(FolioTransaction).filter_by(txn_type="payment").count() == 1


def test_two_catch_ups_post_each_period_once(world):
    with Session(world["engine"]) as db:
        stay_id = check_in(world)(db)["id"]
    later = NOW + timedelta(days=3, hours=1)  # periods 2-4 due

    def view(db):
        return folio_service.view_folio(db, world["principal"], stay_id, now=later)

    race(world["engine"], view, view)
    with Session(world["engine"]) as db:
        periods = [t.period_no for t in db.query(FolioTransaction).filter_by(txn_type="room_charge")]
        assert sorted(periods) == [1, 2, 3, 4]


def test_payment_against_checkout(world):
    with Session(world["engine"]) as db:
        stay_id = check_in(world)(db)["id"]

    def pay(db):
        return folio_service.record_payment(db, world["principal"], stay_id, amount=Decimal("1000"),
                                            method="cash", reference=None, idempotency_key=uuid.uuid4(),
                                            now=NOW, meta=META)

    def checkout(db):
        return stay_service.checkout(db, world["principal"], stay_id, force_reason="Race test",
                                     now=NOW, meta=META)

    race(world["engine"], pay, checkout)
    with Session(world["engine"]) as db:
        balance = stay_service.folio_balance(db, db.get(Stay, stay_id).folio.id)
        assert balance == Decimal("0.00")  # paid in full, whichever ran first
