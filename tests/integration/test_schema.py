"""DB-level rules from data-model.md §4 that the database itself must enforce."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.permissions import ROLE_PERMISSIONS
from app.models import AuditEvent, Folio, FolioTransaction, RolePermission, Stay, User
from tests.factories import make_guest, make_room, make_stay, make_tenant, make_user, daily_plan


def _constraint(exc: IntegrityError) -> str:
    return exc.orig.diag.constraint_name


def test_role_permissions_are_seeded_from_the_catalogue(db):
    rows = db.execute(select(RolePermission.role_code, RolePermission.permission_code)).all()
    seeded = {}
    for role, perm in rows:
        seeded.setdefault(role, set()).add(perm)
    assert seeded == {role: set(perms) for role, perms in ROLE_PERMISSIONS.items()}


def test_email_is_unique_regardless_of_case(db):
    make_user(db, make_tenant(db), email="desk@lodge.com")
    other = make_tenant(db)
    # Insert directly (the factory lowercases): the index must catch a code path that forgets.
    db.add(User(tenant_id=other.id, email="DESK@Lodge.com", name="X", hashed_password="x",
                role_code="receptionist"))
    with pytest.raises(IntegrityError) as exc:
        db.flush()
    assert _constraint(exc.value) == "uq_users_email"


def test_only_one_tenant_admin_per_tenant(db):
    tenant = make_tenant(db)
    make_user(db, tenant, role_code="tenant_admin")
    with pytest.raises(IntegrityError) as exc:
        make_user(db, tenant, role_code="tenant_admin")
    assert _constraint(exc.value) == "uq_one_tenant_admin"


def test_stay_cannot_reference_another_tenants_room(db):
    a, b = make_tenant(db), make_tenant(db)
    user_a = make_user(db, a)
    room_b = make_room(db, b)
    plan_a = daily_plan(db, a)
    db.add(Stay(
        tenant_id=a.id, room_id=room_b.id, guest_id=make_guest(db, a).id, stay_plan_id=plan_a.id,
        actual_check_in_at=datetime(2026, 11, 1, 12, tzinfo=timezone.utc), agreed_price=Decimal("1000"),
        listed_price=Decimal("1000"), occupancy=1, period_hours=24, grace_minutes=30, created_by_user_id=user_a.id,
    ))
    with pytest.raises(IntegrityError) as exc:
        db.flush()
    assert _constraint(exc.value) == "fk_stays_room"


def test_second_active_stay_in_same_room_is_rejected(db):
    tenant = make_tenant(db)
    user = make_user(db, tenant)
    room = make_room(db, tenant)
    make_stay(db, tenant, user, room=room)
    with pytest.raises(IntegrityError) as exc:
        make_stay(db, tenant, user, room=room)
    assert _constraint(exc.value) == "uq_one_active_stay_per_room"


def test_waiver_requires_a_reason(db):
    tenant = make_tenant(db)
    stay = make_stay(db, tenant, make_user(db, tenant))
    folio = db.query(Folio).filter_by(stay_id=stay.id).one()
    charge = FolioTransaction(
        tenant_id=tenant.id, folio_id=folio.id, txn_type="charge", direction="debit", amount=Decimal("200"),
    )
    db.add(charge)
    db.flush()
    db.add(FolioTransaction(
        tenant_id=tenant.id, folio_id=folio.id, txn_type="waiver", direction="credit",
        amount=Decimal("50"), related_txn_id=charge.id,
    ))
    with pytest.raises(IntegrityError) as exc:
        db.flush()
    assert _constraint(exc.value) == "ck_txn_reason_required"


@pytest.mark.parametrize(
    "txn_type,direction,extra",
    [
        ("payment", "credit", {"payment_method": "cash", "period_no": 3}),
        ("charge", "debit", {"period_start_at": datetime(2026, 11, 1, 12, tzinfo=timezone.utc)}),
        ("room_charge", "debit", {"period_no": 1}),  # room charge missing its start time
    ],
)
def test_only_room_charges_carry_period_fields(db, txn_type, direction, extra):
    tenant = make_tenant(db)
    stay = make_stay(db, tenant, make_user(db, tenant))
    folio = db.query(Folio).filter_by(stay_id=stay.id).one()
    db.add(FolioTransaction(
        tenant_id=tenant.id, folio_id=folio.id, txn_type=txn_type, direction=direction,
        amount=Decimal("100"), **extra,
    ))
    with pytest.raises(IntegrityError) as exc:
        db.flush()
    assert _constraint(exc.value) == "ck_txn_period"


def test_waiver_cannot_point_at_itself(db):
    tenant = make_tenant(db)
    stay = make_stay(db, tenant, make_user(db, tenant))
    folio = db.query(Folio).filter_by(stay_id=stay.id).one()
    # The FK alone would accept a self-reference: a row satisfies its own foreign key.
    next_id = db.execute(text("SELECT nextval(pg_get_serial_sequence('folio_transactions', 'id'))")).scalar()
    db.add(FolioTransaction(
        id=next_id, tenant_id=tenant.id, folio_id=folio.id, txn_type="waiver", direction="credit",
        amount=Decimal("50"), related_txn_id=next_id, reason="test",
    ))
    with pytest.raises(IntegrityError) as exc:
        db.flush()
    assert _constraint(exc.value) == "ck_txn_related_earlier"


def test_folio_transactions_are_append_only(db):
    tenant = make_tenant(db)
    stay = make_stay(db, tenant, make_user(db, tenant))
    folio = db.query(Folio).filter_by(stay_id=stay.id).one()
    txn = FolioTransaction(
        tenant_id=tenant.id, folio_id=folio.id, txn_type="charge", direction="debit", amount=Decimal("100"),
    )
    db.add(txn)
    db.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE folio_transactions SET amount = 1 WHERE id = :id"), {"id": txn.id})


@pytest.mark.parametrize("table", ["folio_transactions", "audit_events"])
def test_append_only_tables_cannot_be_truncated(db, table):
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text(f"TRUNCATE {table} CASCADE"))


def test_audit_events_are_append_only(db):
    event = AuditEvent(actor_type="system", action="test.event")
    db.add(event)
    db.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": event.id})
