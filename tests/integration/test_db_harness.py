"""The rollback fixture keeps service commits from leaking out of a test."""
from sqlalchemy import text

from app.models.tenant import Tenant


def test_commit_inside_test_is_not_visible_to_other_connections(db, engine):
    db.add(Tenant(name="Harness Lodge", contact_email="h@example.com", contact_phone="1"))
    db.commit()  # what a service does; here it only releases a savepoint

    assert db.query(Tenant).filter_by(name="Harness Lodge").count() == 1
    with engine.connect() as other:
        seen = other.execute(
            text("SELECT count(*) FROM tenants WHERE name = 'Harness Lodge'")
        ).scalar()
    assert seen == 0
