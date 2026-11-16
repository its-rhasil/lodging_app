"""Keeps the permission catalogue and the error-code map in line with the models."""
from sqlalchemy.dialects import postgresql

import app.models  # noqa: F401
from app.models.ddl import CREATE_FUNCTION_DDL
from app.core.errors import CONSTRAINT_ERRORS
from app.core.permissions import PERMISSIONS, ROLE_PERMISSIONS, ROLES
from app.database import Base


def test_append_only_function_ddl_renders_with_plpgsql_placeholders():
    # Regression: an unescaped % in DDL() raised TypeError, so create_all could not run.
    # The %% here is the driver-level escape: psycopg2 sends a single % to Postgres.
    sql = str(CREATE_FUNCTION_DDL.compile(dialect=postgresql.dialect()))
    assert "'%% is append-only: %% is not allowed'" in sql


def test_every_role_has_a_mapping():
    assert set(ROLE_PERMISSIONS) == set(ROLES)


def test_mapped_permissions_exist_in_catalogue():
    for perms in ROLE_PERMISSIONS.values():
        assert perms <= set(PERMISSIONS)


def test_tenant_admin_has_every_permission():
    assert ROLE_PERMISSIONS["tenant_admin"] == set(PERMISSIONS)


def test_manager_only_permissions_match_architecture():
    extra = ROLE_PERMISSIONS["manager"] - ROLE_PERMISSIONS["receptionist"]
    assert extra == {"stay.backdate", "payment.refund", "folio.reverse", "folio.close_with_balance"}
    assert ROLE_PERMISSIONS["receptionist"] <= ROLE_PERMISSIONS["manager"]


def test_admin_only_permissions_match_architecture():
    extra = ROLE_PERMISSIONS["tenant_admin"] - ROLE_PERMISSIONS["manager"]
    assert extra == {"inventory.manage", "user.manage", "audit.view", "settings.manage"}


def test_every_mapped_constraint_name_exists_in_the_models():
    names = set()
    for table in Base.metadata.tables.values():
        names |= {c.name for c in table.constraints} | {i.name for i in table.indexes}
    missing = set(CONSTRAINT_ERRORS) - names
    assert not missing, f"error map refers to unknown constraints: {missing}"
