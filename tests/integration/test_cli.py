"""create-superadmin, create-tenant (P1-1, P3-1) and reset-password (Day 5)."""
import pytest

from app.cli import main
from app.models import AuditEvent, PlatformUser, StayPlan, Tenant, TenantSettings, User
from app.core.security import verify_password
from tests.factories import make_tenant, make_user

TENANT_ARGS = [
    "create-tenant", "--name", "Sea View Lodge", "--contact-email", "desk@seaview.in",
    "--contact-phone", "9000000000", "--admin-email", "Owner@SeaView.in", "--admin-name", "Owner",
]


def _no_prompt(prompt):
    raise AssertionError("should not prompt when the env var is set")


def test_create_tenant_makes_tenant_settings_daily_plan_and_admin(db, client, capsys):
    code = main(TENANT_ARGS, db=db, environ={"TENANT_ADMIN_PASSWORD": "longenough1"}, getpass=_no_prompt)

    assert code == 0
    tenant = db.query(Tenant).filter_by(name="Sea View Lodge").one()
    assert db.get(TenantSettings, tenant.id).timezone == "Asia/Kolkata"
    plan = db.query(StayPlan).filter_by(tenant_id=tenant.id).one()
    assert (plan.name, plan.period_hours, plan.grace_minutes, plan.is_daily) == ("Full day", 24, 30, True)
    admin = db.query(User).filter_by(tenant_id=tenant.id).one()
    assert (admin.email, admin.role_code) == ("owner@seaview.in", "tenant_admin")
    actions = {e.action for e in db.query(AuditEvent).filter_by(tenant_id=tenant.id)}
    assert actions == {"tenant.created", "user.created"}
    assert "longenough1" not in capsys.readouterr().out

    # The new admin can log in and manage users.
    res = client.post("/auth/login", json={"email": "owner@seaview.in", "password": "longenough1"})
    assert res.status_code == 200 and "user.manage" in res.json()["permissions"]


def test_password_is_prompted_twice_when_no_env_var(db):
    answers = iter(["longenough1", "longenough1"])
    assert main(TENANT_ARGS, db=db, environ={}, getpass=lambda p: next(answers)) == 0


def test_mismatched_prompted_passwords_fail(db, capsys):
    answers = iter(["longenough1", "different1"])
    assert main(TENANT_ARGS, db=db, environ={}, getpass=lambda p: next(answers)) == 1
    assert "don't match" in capsys.readouterr().err
    assert db.query(Tenant).filter_by(name="Sea View Lodge").count() == 0


def test_short_password_creates_nothing(db, capsys):
    assert main(TENANT_ARGS, db=db, environ={"TENANT_ADMIN_PASSWORD": "short"}, getpass=_no_prompt) == 1
    assert "at least 8" in capsys.readouterr().err
    assert db.query(Tenant).filter_by(name="Sea View Lodge").count() == 0


def test_taken_admin_email_rolls_everything_back(db, capsys):
    env = {"TENANT_ADMIN_PASSWORD": "longenough1"}
    assert main(TENANT_ARGS, db=db, environ=env, getpass=_no_prompt) == 0
    second = [a if a != "Sea View Lodge" else "Other Lodge" for a in TENANT_ARGS]

    assert main(second, db=db, environ=env, getpass=_no_prompt) == 1

    assert "already registered" in capsys.readouterr().err
    assert db.query(Tenant).filter_by(name="Other Lodge").count() == 0  # no half-made tenant


def test_create_superadmin_and_log_in(db, client):
    env = {"SUPERADMIN_EMAIL": "Ops@Example.com", "SUPERADMIN_PASSWORD": "longenough1"}
    assert main(["create-superadmin", "--name", "Ops"], db=db, environ=env, getpass=_no_prompt) == 0

    user = db.query(PlatformUser).one()
    assert user.email == "ops@example.com" and verify_password("longenough1", user.hashed_password)
    assert db.query(AuditEvent).filter_by(action="platform_user.created").count() == 1

    res = client.post("/platform/auth/login", json={"email": "ops@example.com", "password": "longenough1"})
    assert res.status_code == 200
    assert "platform_session=" in res.headers["set-cookie"]


def test_create_superadmin_needs_an_email(db, capsys):
    assert main(["create-superadmin", "--name", "Ops"], db=db, environ={"SUPERADMIN_PASSWORD": "x" * 10},
                getpass=_no_prompt) == 1
    assert "SUPERADMIN_EMAIL" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["--admin-email", "--contact-email"])
def test_invalid_email_is_rejected(db, capsys, bad):
    args = list(TENANT_ARGS)
    args[args.index(bad) + 1] = "not-an-email"
    assert main(args, db=db, environ={"TENANT_ADMIN_PASSWORD": "longenough1"}, getpass=_no_prompt) == 1
    assert "Invalid email" in capsys.readouterr().err


# --- reset-password -------------------------------------------------------------------------

RESET = ["reset-password", "--email", "DESK@HillView.in"]  # mixed case: matched case-insensitively
NEW = {"NEW_PASSWORD": "newpassword1"}


@pytest.fixture
def desk_user(db):
    user = make_user(db, make_tenant(db, name="Hill View Lodge"), role_code="receptionist",
                     email="desk@hillview.in", password="oldpassword1")
    db.commit()  # so a failing command's rollback can't undo the setup
    return user


def _login(client, password):
    return client.post("/auth/login", json={"email": "desk@hillview.in", "password": password})


def test_reset_password_sets_the_new_password_and_ends_sessions(db, client, capsys, desk_user):
    assert _login(client, "oldpassword1").status_code == 200  # a live session on this client

    assert main(RESET, db=db, environ=NEW, getpass=_no_prompt) == 0

    out = capsys.readouterr().out
    assert "Hill View Lodge" in out and "logged out everywhere" in out
    assert "newpassword1" not in out
    me = client.get("/auth/me")
    assert (me.status_code, me.json()["code"]) == (401, "session_expired")
    assert _login(client, "oldpassword1").status_code == 401
    assert _login(client, "newpassword1").status_code == 200
    [event] = db.query(AuditEvent).filter_by(action="user.password_reset").all()
    assert (event.tenant_id, event.actor_type, event.entity_id) == (desk_user.tenant_id, "system", str(desk_user.id))
    assert "newpassword1" not in (event.summary or "")


def test_reset_password_for_an_unknown_email_changes_nothing(db, capsys):
    args = ["reset-password", "--email", "nobody@example.com"]
    assert main(args, db=db, environ=NEW, getpass=_no_prompt) == 1
    assert "No user with that email" in capsys.readouterr().err
    assert db.query(AuditEvent).filter_by(action="user.password_reset").count() == 0


def test_reset_password_too_short_changes_nothing(db, client, capsys, desk_user):
    assert _login(client, "oldpassword1").status_code == 200

    assert main(RESET, db=db, environ={"NEW_PASSWORD": "short"}, getpass=_no_prompt) == 1

    assert "at least 8" in capsys.readouterr().err
    assert client.get("/auth/me").status_code == 200  # the session survived
    assert _login(client, "oldpassword1").status_code == 200
    assert db.query(AuditEvent).filter_by(action="user.password_reset").count() == 0


def test_reset_password_asks_twice_without_the_env_var(db, client, desk_user):
    answers = iter(["newpassword1", "newpassword1"])
    assert main(RESET, db=db, environ={}, getpass=lambda p: next(answers)) == 0
    assert _login(client, "newpassword1").status_code == 200


def test_reset_password_with_mismatched_prompts_changes_nothing(db, client, capsys, desk_user):
    answers = iter(["newpassword1", "different1"])
    assert main(RESET, db=db, environ={}, getpass=lambda p: next(answers)) == 1
    assert "don't match" in capsys.readouterr().err
    assert _login(client, "oldpassword1").status_code == 200


def test_reset_password_warns_when_the_account_is_deactivated(db, capsys, desk_user):
    desk_user.is_active = False
    db.commit()
    assert main(RESET, db=db, environ=NEW, getpass=_no_prompt) == 0
    assert "deactivated" in capsys.readouterr().out
