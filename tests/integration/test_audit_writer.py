import pytest
from sqlalchemy.exc import IntegrityError

from app.core.request_context import RequestMeta
from app.models import AuditEvent
from app.service import audit_service
from app.service.audit_service import ANONYMOUS, SYSTEM, Actor
from tests.factories import make_tenant, make_user


def test_record_writes_actor_entity_and_request_metadata(db):
    tenant = make_tenant(db)
    user = make_user(db, tenant)
    audit_service.record(
        db, action="user.created", actor=Actor.tenant_user(user.id), tenant_id=tenant.id,
        entity_type="user", entity_id=user.id, summary="Created user",
        changes={"role_code": [None, "receptionist"]},
        meta=RequestMeta(request_id="r1", ip="203.0.113.7", user_agent="pytest"),
    )
    db.flush()
    event = db.query(AuditEvent).filter_by(action="user.created").one()
    assert (event.actor_type, event.actor_user_id, event.tenant_id) == ("tenant_user", user.id, tenant.id)
    assert event.entity_id == str(user.id)
    assert event.changes == {"role_code": [None, "receptionist"]}
    assert (event.request_id, str(event.ip), event.user_agent) == ("r1", "203.0.113.7", "pytest")


def test_system_and_anonymous_actors_need_no_ids(db):
    audit_service.record(db, action="tenant.created", actor=SYSTEM, tenant_id=None)
    audit_service.record(db, action="auth.login.failed", actor=ANONYMOUS, tenant_id=None)
    db.flush()
    assert db.query(AuditEvent).count() >= 2


def test_record_does_not_commit(db):
    audit_service.record(db, action="x.test", actor=SYSTEM, tenant_id=None)
    assert db.new  # still pending in the session: the caller's commit saves it


@pytest.mark.parametrize("changes", [
    {"password": ["a", "b"]},
    {"hashed_password": [None, "x"]},
    {"session": {"token_hash": "x"}},
])
def test_secrets_are_refused_in_changes(db, changes):
    with pytest.raises(ValueError, match="secret"):
        audit_service.record(db, action="x.test", actor=SYSTEM, tenant_id=None, changes=changes)


def test_inconsistent_actor_is_rejected_by_the_database(db):
    audit_service.record(db, action="x.test", actor=Actor("tenant_user"), tenant_id=None)  # no user id
    with pytest.raises(IntegrityError) as exc:
        db.flush()
    assert exc.value.orig.diag.constraint_name == "ck_audit_actor_ids"
