"""Shared fixtures: test engine, per-test rollback session, API client.

How isolation works:
- `engine` (once per run) rebuilds the schema in the test DB from the models.
- `db` (per test) opens one connection and an outer transaction. The Session
  joins it with join_transaction_mode="create_savepoint", so a service's
  db.commit() only releases a savepoint. The outer transaction is rolled back
  after the test: nothing a test writes survives it.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import settings
from app.core.permissions import PERMISSIONS, ROLE_PERMISSIONS, ROLES
from app.models import Permission, Role, RolePermission
from app.database import Base, get_db
from tests.db_guard import assert_safe_test_database_url


@pytest.fixture(scope="session")
def engine():
    url = settings.test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set: database tests skipped.")
    try:
        assert_safe_test_database_url(url, settings.database_url)
    except ValueError as exc:
        pytest.exit(f"Refusing to run database tests: {exc}", returncode=2)

    eng = create_engine(url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)  # also installs the append-only triggers (app/models/ddl.py)
    with eng.begin() as conn:
        _seed_rbac(conn)
    yield eng
    eng.dispose()


def _seed_rbac(conn) -> None:
    """Same rows the baseline migration seeds, taken from the catalogue in code."""
    conn.execute(insert(Role), [
        {"code": code, "name": name, "description": desc} for code, (name, desc) in ROLES.items()
    ])
    conn.execute(insert(Permission), [
        {"code": code, "description": desc} for code, desc in PERMISSIONS.items()
    ])
    conn.execute(insert(RolePermission), [
        {"role_code": role, "permission_code": perm}
        for role, perms in ROLE_PERMISSIONS.items() for perm in sorted(perms)
    ])


@pytest.fixture
def db(engine):
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


class FakeClock:
    """Stands in for app.core.clock.get_now in tests. Always timezone-aware (UTC)."""

    def __init__(self, now: datetime):
        self.current = now

    def now(self) -> datetime:
        return self.current

    def set(self, value: datetime) -> None:
        self.current = value

    def advance(self, **delta) -> None:
        self.current += timedelta(**delta)


@pytest.fixture
def fake_clock():
    return FakeClock(datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc))


@pytest.fixture
def client(db, fake_clock):
    # Imported lazily so unit tests don't depend on every route module importing cleanly.
    from fastapi.testclient import TestClient
    from app.core.clock import get_now
    from app.main import app

    def _override_get_db():
        # Same as the real get_db(): a failed request rolls back to the last commit.
        # Data a test only flushed is undone too, so a test that keeps using it after
        # a failing request should db.commit() its setup first.
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_now] = fake_clock.now
    # https base URL: the session cookie is Secure, so the client only sends it over https.
    with TestClient(app, base_url="https://testserver") as c:
        yield c
    app.dependency_overrides.clear()
