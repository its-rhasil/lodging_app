"""Database objects that aren't tables: the append-only triggers (DL-P13).

Each append-only table gets two triggers that call the same function:
- a row trigger that blocks UPDATE and DELETE;
- a statement trigger that blocks TRUNCATE.

Autogenerate can't see these. The baseline migration gets the same SQL through
the manual-additions snippet. The listeners below only fire on
Base.metadata.create_all(), which the test suite uses to build its schema,
so tests run against the same triggers as the real database.
"""
from sqlalchemy import DDL, event

from app.database import Base

APPEND_ONLY_TABLES = ("folio_transactions", "audit_events")

CREATE_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION forbid_update_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP;
END;
$$
"""
DROP_APPEND_ONLY_FUNCTION = "DROP FUNCTION IF EXISTS forbid_update_delete()"


def create_append_only_trigger(table: str) -> str:
    return (
        f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION forbid_update_delete()"
    )


def create_no_truncate_trigger(table: str) -> str:
    # TRUNCATE skips row triggers, so it needs its own statement-level trigger.
    return (
        f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION forbid_update_delete()"
    )


# DDL() runs Python %-formatting on its statement, so plpgsql's literal % must be doubled.
CREATE_FUNCTION_DDL = DDL(CREATE_APPEND_ONLY_FUNCTION.replace("%", "%%"))

event.listen(Base.metadata, "before_create", CREATE_FUNCTION_DDL)
for _table in APPEND_ONLY_TABLES:
    event.listen(Base.metadata.tables[_table], "after_create", DDL(create_append_only_trigger(_table)))
    event.listen(Base.metadata.tables[_table], "after_create", DDL(create_no_truncate_trigger(_table)))
event.listen(Base.metadata, "after_drop", DDL(DROP_APPEND_ONLY_FUNCTION))
