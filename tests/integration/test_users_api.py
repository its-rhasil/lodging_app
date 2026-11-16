"""Users API: who may call it, what it does, and its guardrails (testing-strategy.md §8)."""
import pytest

from app.models import AuditEvent, User, UserSession
from tests.factories import DEFAULT_PASSWORD, add_override, log_in, make_session, make_tenant, make_user

NEW_USER = {"email": "New.Desk@Lodge.com", "name": "New Desk", "password": "longenough1", "role_code": "receptionist"}


@pytest.fixture
def tenant(db):
    return make_tenant(db)


@pytest.fixture
def admin(db, tenant):
    return make_user(db, tenant, role_code="tenant_admin")


@pytest.fixture
def as_admin(db, client, admin):
    log_in(client, db, admin)
    return client


def _manager_with_user_manage(db, client, tenant):
    """A manager given user.manage, to exercise guardrails the admin can't trip on themselves."""
    manager = make_user(db, tenant, role_code="manager")
    add_override(db, manager, "user.manage", "grant")
    log_in(client, db, manager)
    return manager


# --- access --------------------------------------------------------------

@pytest.mark.parametrize("role", ["receptionist", "manager"])
@pytest.mark.parametrize("method,path", [("get", "/users"), ("post", "/users")])
def test_only_user_managers_can_use_the_users_api(db, client, tenant, role, method, path):
    log_in(client, db, make_user(db, tenant, role_code=role))
    res = client.request(method, path, json=NEW_USER)
    assert res.status_code == 403


# --- create --------------------------------------------------------------

def test_admin_creates_a_receptionist_who_can_log_in(db, as_admin, tenant, admin):
    res = as_admin.post("/users", json=NEW_USER)

    assert res.status_code == 201
    body = res.json()
    assert (body["email"], body["role_code"], body["is_active"]) == ("new.desk@lodge.com", "receptionist", True)
    created = db.get(User, body["id"])
    assert created.tenant_id == tenant.id  # from the session, never from the body
    event = db.query(AuditEvent).filter_by(action="user.created").one()
    assert (event.actor_user_id, event.entity_id) == (admin.id, str(created.id))
    assert "password" not in str(event.changes)

    as_admin.cookies.clear()
    assert as_admin.post("/auth/login", json={"email": "new.desk@lodge.com", "password": "longenough1"}).status_code == 200


def test_tenant_admin_role_cannot_be_created(as_admin):
    res = as_admin.post("/users", json={**NEW_USER, "role_code": "tenant_admin"})
    assert res.status_code == 422


def test_short_password_is_rejected(as_admin):
    res = as_admin.post("/users", json={**NEW_USER, "password": "short"})
    assert (res.status_code, res.json()["code"]) == (422, "password_too_short")


def test_email_taken_in_any_tenant_any_case_is_409(db, as_admin):
    make_user(db, make_tenant(db), email="new.desk@lodge.com")
    db.commit()  # keep setup data: the failing request rolls back to the last commit
    res = as_admin.post("/users", json=NEW_USER)
    assert (res.status_code, res.json()["code"]) == (409, "email_taken")


# --- list / detail ------------------------------------------------------

def test_list_shows_only_own_tenant(db, as_admin, admin):
    make_user(db, make_tenant(db))  # someone in another lodge
    ids = [u["id"] for u in as_admin.get("/users").json()]
    assert ids == [admin.id]


def test_other_tenants_user_is_not_found(db, as_admin):
    stranger = make_user(db, make_tenant(db))
    db.commit()  # each 404 below rolls back to the last commit
    for res in (as_admin.get(f"/users/{stranger.id}"), as_admin.post(f"/users/{stranger.id}/deactivate"),
                as_admin.put(f"/users/{stranger.id}/overrides", json={"overrides": []})):
        assert (res.status_code, res.json()["code"]) == (404, "user_not_found")


# --- deactivate ----------------------------------------------------------

def test_deactivate_revokes_every_session_and_audits(db, as_admin, tenant):
    target = make_user(db, tenant)
    _, s1 = make_session(db, target)
    _, s2 = make_session(db, target)

    res = as_admin.post(f"/users/{target.id}/deactivate")

    assert res.status_code == 200 and res.json()["is_active"] is False
    for s in (s1, s2):
        db.refresh(s)
        assert s.revoked_at is not None
    assert db.query(AuditEvent).filter_by(action="user.deactivated", entity_id=str(target.id)).count() == 1


def test_admin_cannot_deactivate_themselves(as_admin, admin):
    res = as_admin.post(f"/users/{admin.id}/deactivate")
    assert (res.status_code, res.json()["code"]) == (422, "cannot_deactivate_self")


def test_tenant_admin_cannot_be_deactivated_by_tenant_users(db, client, tenant, admin):
    _manager_with_user_manage(db, client, tenant)
    res = client.post(f"/users/{admin.id}/deactivate")
    assert (res.status_code, res.json()["code"]) == (403, "cannot_deactivate_tenant_admin")


# --- overrides -----------------------------------------------------------

def test_grant_and_deny_change_effective_permissions(db, as_admin, tenant):
    target = make_user(db, tenant, role_code="receptionist")
    res = as_admin.put(f"/users/{target.id}/overrides", json={"overrides": [
        {"permission_code": "payment.refund", "effect": "grant", "reason": "Night shift lead"},
        {"permission_code": "folio.waive", "effect": "deny"},
    ]})

    assert res.status_code == 200
    body = res.json()
    assert "payment.refund" in body["permissions"] and "folio.waive" not in body["permissions"]
    assert {(o["permission_code"], o["effect"]) for o in body["overrides"]} == {
        ("payment.refund", "grant"), ("folio.waive", "deny"),
    }
    event = db.query(AuditEvent).filter_by(action="user.permissions.updated").one()
    assert event.changes == {"overrides": [[], ["deny:folio.waive", "grant:payment.refund"]]}


def test_put_replaces_the_whole_list(db, as_admin, tenant):
    target = make_user(db, tenant)
    add_override(db, target, "payment.refund", "grant")
    body = as_admin.put(f"/users/{target.id}/overrides", json={"overrides": []}).json()
    assert body["overrides"] == [] and "payment.refund" not in body["permissions"]


def test_new_permissions_apply_to_the_users_next_request(db, as_admin, tenant):
    target = make_user(db, tenant, role_code="receptionist")
    token, _ = make_session(db, target)
    as_admin.put(f"/users/{target.id}/overrides", json={"overrides": [
        {"permission_code": "payment.refund", "effect": "grant"},
    ]})
    as_admin.cookies.set("access_token", token)
    assert "payment.refund" in as_admin.get("/auth/me").json()["permissions"]


@pytest.mark.parametrize("overrides,code", [
    ([{"permission_code": "folio.wave", "effect": "deny"}], "unknown_permission"),
    ([{"permission_code": "folio.waive", "effect": "deny"},
      {"permission_code": "folio.waive", "effect": "grant"}], "duplicate_permission"),
])
def test_bad_override_lists_are_rejected(db, as_admin, tenant, overrides, code):
    target = make_user(db, tenant)
    res = as_admin.put(f"/users/{target.id}/overrides", json={"overrides": overrides})
    assert (res.status_code, res.json()["code"]) == (422, code)


def test_tenant_admin_overrides_cannot_be_changed(db, client, tenant, admin):
    _manager_with_user_manage(db, client, tenant)
    res = client.put(f"/users/{admin.id}/overrides", json={"overrides": [
        {"permission_code": "user.manage", "effect": "deny"},
    ]})
    assert (res.status_code, res.json()["code"]) == (403, "cannot_override_tenant_admin")


def test_nobody_edits_their_own_overrides(db, client, tenant):
    manager = _manager_with_user_manage(db, client, tenant)
    res = client.put(f"/users/{manager.id}/overrides", json={"overrides": [
        {"permission_code": "settings.manage", "effect": "grant"},
    ]})
    assert (res.status_code, res.json()["code"]) == (403, "cannot_override_self")


def test_cannot_grant_a_permission_you_do_not_hold(db, client, tenant):
    _manager_with_user_manage(db, client, tenant)
    target = make_user(db, tenant, role_code="receptionist")
    res = client.put(f"/users/{target.id}/overrides", json={"overrides": [
        {"permission_code": "settings.manage", "effect": "grant"},  # managers don't have it
    ]})
    assert (res.status_code, res.json()["code"]) == (403, "cannot_grant_unheld")
    assert res.json()["details"] == {"permissions": ["settings.manage"]}
