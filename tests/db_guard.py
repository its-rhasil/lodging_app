"""Protects real data: the suite only ever runs against a dedicated test database."""
from sqlalchemy.engine import make_url


def assert_safe_test_database_url(test_url: str, app_url: str) -> None:
    """Raise ValueError unless test_url points at a separate database named like a test DB."""
    test = make_url(test_url)
    app = make_url(app_url)

    if not test.database or "test" not in test.database.lower():
        raise ValueError(
            f"TEST_DATABASE_URL database name must contain 'test' (got {test.database!r})."
        )
    same_server = (test.host, test.port) == (app.host, app.port)
    if same_server and test.database == app.database:
        raise ValueError("TEST_DATABASE_URL points at the same database as DATABASE_URL.")
