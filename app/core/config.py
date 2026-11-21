from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    # Separate database used only by the test suite (must contain "test").
    test_database_url: str | None = None

    # SQL statement logging. Off by default: it floods logs and can leak data (D-11).
    db_echo: bool = False

    # Session lifetime (D-18): one 8-hour shift, counted from login. No idle timeout.
    session_expires_minutes: int = 480

    # Session cookie. Secure by default; set COOKIE_SECURE=false only for local http.
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict"] = "lax"

    # Production: the PWA's origin, e.g. https://app.<domain> (architecture.md §6.2). CORS allows
    # exactly this origin, with credentials. Unset in development: Vite proxies /api (same origin).
    frontend_origin: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def session_max_age_seconds(self) -> int:
        """Cookie max_age, aligned with the server-side absolute session lifetime."""
        return self.session_expires_minutes * 60


settings = Settings()
