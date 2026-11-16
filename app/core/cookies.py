"""Session cookie helpers. All cookie attributes come from settings (D-18)."""
from fastapi import Response

from app.core.config import settings

TENANT_SESSION_COOKIE = "access_token"
PLATFORM_SESSION_COOKIE = "platform_session"  # separate cookie for superadmins (DL-P07)


def set_session_cookie(response: Response, token: str, name: str = TENANT_SESSION_COOKIE) -> None:
    response.set_cookie(
        key=name,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_max_age_seconds,
    )


def clear_session_cookie(response: Response, name: str = TENANT_SESSION_COOKIE) -> None:
    response.delete_cookie(
        key=name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
