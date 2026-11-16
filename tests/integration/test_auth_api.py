"""Login, logout, /auth/me and session checks (testing-strategy.md §8)."""
from datetime import timedelta

import pytest

from app.core.config import settings
from app.core.security import utcnow
from app.models import AuditEvent, UserSession
from app.service import auth_service
from tests.factories import DEFAULT_PASSWORD, log_in, make_session, make_tenant, make_user


def _login(client, email, password=DEFAULT_PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _events(db, action):
    return db.query(AuditEvent).filter_by(action=action).order_by(AuditEvent.id).all()


# --- login ---------------------------------------------------------------

def test_login_sets_the_cookie_returns_the_profile_and_audits(db, client):
    user = make_user(db, make_tenant(db), role_code="manager", email="desk@lodge.com")
    res = _login(client, "desk@lodge.com")

    assert res.status_code == 200
    body = res.json()
    assert (body["id"], body["role_code"]) == (user.id, "manager")
    assert "payment.refund" in body["permissions"] and "user.manage" not in body["permissions"]

    cookie = res.headers["set-cookie"].lower()
    assert "access_token=" in cookie and "httponly" in cookie and "secure" in cookie
    assert f"max-age={settings.session_max_age_seconds}" in cookie

    [event] = _events(db, "auth.login")
    assert (event.actor_type, event.actor_user_id, event.tenant_id) == ("tenant_user", user.id, user.tenant_id)
    assert event.request_id == res.headers["x-request-id"]


def test_login_email_is_case_insensitive(db, client):
    make_user(db, make_tenant(db), email="desk@lodge.com")
    assert _login(client, "  Desk@LODGE.com ").status_code == 200


@pytest.mark.parametrize("email,password", [
    ("desk@lodge.com", "wrong-password"),   # known email, wrong password
    ("nobody@lodge.com", DEFAULT_PASSWORD),  # unknown email
])
def test_wrong_password_and_unknown_email_look_the_same(db, client, monkeypatch, email, password):
    make_user(db, make_tenant(db), email="desk@lodge.com")
    calls = []
    real_verify = auth_service.verify_password
    monkeypatch.setattr(auth_service, "verify_password", lambda p, h: calls.append(h) or real_verify(p, h))

    res = _login(client, email, password)

    assert res.status_code == 401
    assert res.json() == {"code": "invalid_credentials", "message": "Invalid email or password.", "details": None}
    assert len(calls) == 1  # a bcrypt check runs in both cases: same timing
    assert "set-cookie" not in res.headers
    [event] = _events(db, "auth.login.failed")
    assert event.actor_type == "anonymous"


def test_failed_login_for_a_known_user_goes_to_their_tenants_trail(db, client):
    user = make_user(db, make_tenant(db), email="desk@lodge.com")
    _login(client, "desk@lodge.com", "wrong-password")
    [event] = _events(db, "auth.login.failed")
    assert (event.tenant_id, event.entity_type, event.entity_id) == (user.tenant_id, "user", str(user.id))
    assert "wrong-password" not in (event.summary or "")


def test_deactivated_user_cannot_log_in(db, client):
    make_user(db, make_tenant(db), email="desk@lodge.com", is_active=False)
    res = _login(client, "desk@lodge.com")
    assert (res.status_code, res.json()["code"]) == (401, "account_inactive")


def test_suspended_tenant_cannot_log_in(db, client):
    make_user(db, make_tenant(db, status="suspended"), email="desk@lodge.com")
    res = _login(client, "desk@lodge.com")
    assert (res.status_code, res.json()["code"]) == (401, "tenant_suspended")


def test_malformed_email_is_a_validation_error(client):
    assert _login(client, "not-an-email").status_code == 422


def test_public_signup_route_is_gone(client):
    assert client.post("/auth/signup-tenant", json={}).status_code == 404


# --- sessions --------------------------------------------------------------

def test_me_returns_the_profile(db, client):
    user = make_user(db, make_tenant(db), role_code="tenant_admin")
    log_in(client, db, user)
    body = client.get("/auth/me").json()
    assert body["id"] == user.id and "user.manage" in body["permissions"]


def test_me_without_a_cookie_is_401(client):
    res = client.get("/auth/me")
    assert (res.status_code, res.json()["code"]) == (401, "not_authenticated")


@pytest.mark.parametrize("fields", [
    {"expires_at": utcnow() - timedelta(minutes=1)},  # past its expiry
    {"revoked_at": utcnow()},                         # logged out
])
def test_dead_sessions_are_rejected(db, client, fields):
    token, _ = make_session(db, make_user(db, make_tenant(db)), **fields)
    client.cookies.set("access_token", token)
    res = client.get("/auth/me")
    assert (res.status_code, res.json()["code"]) == (401, "session_expired")


def test_login_session_expires_one_lifetime_after_login(db, client):
    user = make_user(db, make_tenant(db), email="desk@lodge.com")
    before = utcnow()
    _login(client, "desk@lodge.com")
    session = db.query(UserSession).filter_by(user_id=user.id).one()
    lifetime = session.expires_at - before
    assert timedelta(minutes=settings.session_expires_minutes) <= lifetime < \
        timedelta(minutes=settings.session_expires_minutes, seconds=30)


def test_unused_session_still_works_until_expiry(db, client):
    # No idle timeout: a session opened hours ago and not used since is still valid.
    token, _ = make_session(
        db, make_user(db, make_tenant(db)),
        created_at=utcnow() - timedelta(hours=7), expires_at=utcnow() + timedelta(minutes=5),
    )
    client.cookies.set("access_token", token)
    assert client.get("/auth/me").status_code == 200


def test_existing_session_stops_working_when_user_is_deactivated(db, client):
    user = make_user(db, make_tenant(db))
    log_in(client, db, user)
    user.is_active = False
    db.flush()
    assert client.get("/auth/me").json()["code"] == "account_inactive"


def test_existing_session_stops_working_when_tenant_is_suspended(db, client):
    tenant = make_tenant(db)
    log_in(client, db, make_user(db, tenant))
    tenant.status = "suspended"
    db.flush()
    assert client.get("/auth/me").json()["code"] == "tenant_suspended"


# --- logout ----------------------------------------------------------------

def test_logout_revokes_the_session_and_audits(db, client):
    user = make_user(db, make_tenant(db), email="desk@lodge.com")
    _login(client, "desk@lodge.com")

    res = client.post("/auth/logout")

    assert res.status_code == 204
    session = db.query(UserSession).filter_by(user_id=user.id).one()
    assert session.revoked_at is not None
    [event] = _events(db, "auth.logout")
    assert event.actor_user_id == user.id
    assert client.get("/auth/me").status_code == 401


def test_logout_without_a_session_still_succeeds(client):
    assert client.post("/auth/logout").status_code == 204
