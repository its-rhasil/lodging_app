"""Superadmin login is separate from tenant login (DL-P07)."""
import pytest

from app.models import AuditEvent, PlatformUser
from app.service import platform_service
from tests.factories import log_in, make_tenant, make_user

PASSWORD = "longenough1"


@pytest.fixture
def superadmin(db) -> PlatformUser:
    return platform_service.create_superadmin(db, email="ops@example.com", name="Ops", password=PASSWORD)


def _login(client, email="ops@example.com", password=PASSWORD):
    return client.post("/platform/auth/login", json={"email": email, "password": password})


def test_login_me_logout(db, client, superadmin):
    res = _login(client)
    assert res.status_code == 200 and res.json()["email"] == "ops@example.com"
    db.refresh(superadmin)
    assert superadmin.last_login_at is not None
    event = db.query(AuditEvent).filter_by(action="platform.auth.login").one()
    assert (event.actor_type, event.actor_platform_user_id, event.tenant_id) == ("platform_user", superadmin.id, None)

    assert client.get("/platform/auth/me").json()["id"] == superadmin.id

    assert client.post("/platform/auth/logout").status_code == 204
    assert db.query(AuditEvent).filter_by(action="platform.auth.logout").count() == 1
    assert client.get("/platform/auth/me").status_code == 401


@pytest.mark.parametrize("email,password", [("ops@example.com", "wrong-pass"), ("nobody@example.com", PASSWORD)])
def test_bad_credentials_look_the_same_and_are_audited(db, client, superadmin, email, password):
    res = _login(client, email, password)
    assert (res.status_code, res.json()["code"]) == (401, "invalid_credentials")
    assert db.query(AuditEvent).filter_by(action="platform.auth.login.failed").count() == 1


def test_tenant_staff_cannot_use_platform_login(db, client):
    make_user(db, make_tenant(db), email="desk@lodge.com")
    assert _login(client, "desk@lodge.com", "password123").status_code == 401


def test_tenant_cookie_does_not_open_platform_routes(db, client):
    log_in(client, db, make_user(db, make_tenant(db), role_code="tenant_admin"))
    assert client.get("/platform/auth/me").status_code == 401


def test_platform_cookie_does_not_open_tenant_routes(db, client, superadmin):
    _login(client)
    assert client.get("/auth/me").status_code == 401
    assert client.get("/users").status_code == 401
