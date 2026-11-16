import pytest
from fastapi import Response

from app.core.config import Settings
from app.core import cookies
from tests.db_guard import assert_safe_test_database_url


def _settings(**overrides) -> Settings:
    # _env_file=None: test the code defaults, not the developer's .env
    return Settings(_env_file=None, database_url="postgresql://u@localhost/lodging", **overrides)


def test_sql_echo_is_off_by_default():
    assert _settings().db_echo is False


def test_cookie_is_secure_by_default():
    assert _settings().cookie_secure is True


def test_session_lifetime_default_is_one_8_hour_shift():
    assert _settings().session_expires_minutes == 480


def test_cookie_max_age_matches_session_lifetime():
    s = _settings(session_expires_minutes=600)
    assert s.session_max_age_seconds == 600 * 60


def test_session_cookie_attributes_come_from_settings(monkeypatch):
    monkeypatch.setattr(cookies, "settings", _settings(session_expires_minutes=60))
    response = Response()
    cookies.set_session_cookie(response, "tok")
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "secure" in header
    assert "samesite=lax" in header
    assert "max-age=3600" in header


@pytest.mark.parametrize(
    "test_url",
    [
        "postgresql://u@localhost/lodging",          # same DB as the app
        "postgresql://u@localhost/lodging_dev",      # no 'test' in the name
    ],
)
def test_guard_refuses_unsafe_test_database(test_url):
    with pytest.raises(ValueError):
        assert_safe_test_database_url(test_url, "postgresql://u@localhost/lodging")


def test_guard_accepts_separate_test_database():
    assert_safe_test_database_url(
        "postgresql://u@localhost/lodging_test", "postgresql://u@localhost/lodging"
    )
