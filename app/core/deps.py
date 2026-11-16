"""Request dependencies: who is calling, and may they do this (architecture.md §5, §6.4).

Every route declares one of:
- Depends(require_permission("<code>")) for tenant endpoints;
- Depends(require_platform_user) for platform (superadmin) endpoints;
- Depends(get_current_principal) only for "about me" endpoints (e.g. /auth/me);
- nothing, only for the public allow-list (login, logout, health).
tests/unit/test_route_guards.py checks this for every route in the app.
"""
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.cookies import PLATFORM_SESSION_COOKIE, TENANT_SESSION_COOKIE
from app.core.errors import PermissionDenied
from app.core.permissions import PERMISSIONS
from app.core.principal import Principal
from app.database import get_db
from app.service import auth_service, platform_service


def get_current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    return auth_service.authenticate_session(db, request.cookies.get(TENANT_SESSION_COOKIE))


def require_platform_user(request: Request, db: Session = Depends(get_db)) -> Principal:
    """Platform endpoints. Only the platform cookie counts; a tenant cookie is ignored."""
    return platform_service.authenticate_session(db, request.cookies.get(PLATFORM_SESSION_COOKIE))


require_platform_user.platform_guard = True  # read by the route-guard test


def require_permission(code: str):
    """Dependency factory. Unknown codes fail at import time, so a typo can't ship."""
    if code not in PERMISSIONS:
        raise ValueError(f"Unknown permission code: {code!r}")

    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not principal.has(code):
            raise PermissionDenied(
                "You don't have permission to do this.", details={"permission": code},
            )
        return principal

    dependency.required_permission = code  # read by the route-guard test
    return dependency
