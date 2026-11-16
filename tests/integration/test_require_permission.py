"""require_permission() end to end, on a throwaway route that needs a manager-only permission."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.deps import require_permission
from app.core.errors import register_error_handlers
from app.core.principal import Principal
from app.database import get_db
from tests.factories import add_override, log_in, make_tenant, make_user


@pytest.fixture
def refund_client(db):
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/refund")
    def refund(principal: Principal = Depends(require_permission("payment.refund"))):
        return {"user_id": principal.user_id}

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def test_receptionist_is_denied_a_manager_only_permission(db, refund_client):
    log_in(refund_client, db, make_user(db, make_tenant(db), role_code="receptionist"))
    res = refund_client.post("/refund")
    assert res.status_code == 403
    assert res.json()["code"] == "permission_denied"
    assert res.json()["details"] == {"permission": "payment.refund"}


def test_manager_is_allowed(db, refund_client):
    user = make_user(db, make_tenant(db), role_code="manager")
    log_in(refund_client, db, user)
    assert refund_client.post("/refund").json() == {"user_id": user.id}


def test_grant_lets_a_receptionist_refund(db, refund_client):
    user = make_user(db, make_tenant(db), role_code="receptionist")
    add_override(db, user, "payment.refund", "grant")
    log_in(refund_client, db, user)
    assert refund_client.post("/refund").status_code == 200


def test_deny_stops_a_manager_refunding(db, refund_client):
    user = make_user(db, make_tenant(db), role_code="manager")
    add_override(db, user, "payment.refund", "deny")
    log_in(refund_client, db, user)
    assert refund_client.post("/refund").status_code == 403


def test_no_cookie_is_401_not_403(refund_client):
    res = refund_client.post("/refund")
    assert res.status_code == 401
    assert res.json()["code"] == "not_authenticated"
