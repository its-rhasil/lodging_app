"""Tenant staff authentication: login, logout, session validation (architecture.md §6.2).

Error codes the frontend can rely on:
- invalid_credentials: unknown email or wrong password (same message for both);
- account_inactive / tenant_suspended: correct password, but login isn't allowed;
- not_authenticated: no cookie or an unknown token;
- session_expired: past the expiry (fixed at login) or logged out.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotAuthenticated
from app.core.principal import ANONYMOUS, Actor, Principal
from app.core.request_context import RequestMeta
from app.core.security import (
    dummy_password_hash, generate_token, get_token_expiry, hash_token, normalize_email, utcnow,
    verify_password,
)
from app.models import Tenant, User, UserSession
from app.service import audit_service, permission_service

INVALID_CREDENTIALS = "Invalid email or password."


def login(db: Session, *, email: str, password: str, meta: RequestMeta) -> tuple[str, User]:
    """Returns (raw session token, user). Every outcome is audited and committed."""
    email = normalize_email(email)
    user = db.scalars(select(User).where(func.lower(User.email) == email)).first()

    if user is None:
        verify_password(password, dummy_password_hash())  # same bcrypt cost as a real check
        _login_failed(db, meta, email, user=None, cause="unknown email")
    if not verify_password(password, user.hashed_password):
        _login_failed(db, meta, email, user=user, cause="wrong password")
    if not user.is_active:
        _login_failed(db, meta, email, user=user, cause="user deactivated",
                      code="account_inactive", message="This account is deactivated.")
    tenant = db.get(Tenant, user.tenant_id)
    if tenant.status != "active":
        _login_failed(db, meta, email, user=user, cause="tenant suspended",
                      code="tenant_suspended", message="This lodge's account is suspended.")

    raw_token = generate_token()
    session = UserSession(user_id=user.id, token_hash=hash_token(raw_token), expires_at=get_token_expiry())
    db.add(session)
    db.flush()
    audit_service.record(
        db, action="auth.login", actor=Actor.tenant_user(user.id), tenant_id=user.tenant_id,
        entity_type="user", entity_id=user.id, summary=f"{user.email} logged in", meta=meta,
    )
    db.commit()
    return raw_token, user


def _login_failed(db: Session, meta: RequestMeta, email: str, *, user: User | None, cause: str,
                  code: str = "invalid_credentials", message: str = INVALID_CREDENTIALS) -> None:
    # Known users: the event goes to their tenant's trail. Unknown emails have no tenant.
    audit_service.record(
        db, action="auth.login.failed", actor=ANONYMOUS,
        tenant_id=user.tenant_id if user else None,
        entity_type="user" if user else None, entity_id=user.id if user else None,
        summary=f"Failed login for {email[:254]}: {cause}", meta=meta,
    )
    db.commit()  # the failure is the whole use case: save its audit row, then refuse
    raise NotAuthenticated(message, code=code)


def logout(db: Session, *, token: str | None, meta: RequestMeta) -> None:
    """Revoke the session behind the cookie, if it is still live. Never fails."""
    if not token:
        return
    session = db.scalars(
        select(UserSession).where(UserSession.token_hash == hash_token(token), UserSession.revoked_at.is_(None))
    ).first()
    if session is None:
        return
    user = db.get(User, session.user_id)
    session.revoked_at = utcnow()
    audit_service.record(
        db, action="auth.logout", actor=Actor.tenant_user(user.id), tenant_id=user.tenant_id,
        entity_type="user", entity_id=user.id, summary=f"{user.email} logged out", meta=meta,
    )
    db.commit()


def check_session_alive(session) -> None:
    """Shared by tenant and platform sessions: revoked or expired -> session_expired."""
    if session.revoked_at is not None or session.expires_at <= utcnow():
        raise NotAuthenticated("Your session has ended. Please log in again.", code="session_expired")


def profile(db: Session, user_id: int, permissions: frozenset[str] | None = None) -> dict:
    """What /auth/login and /auth/me return about the logged-in user."""
    user = db.get(User, user_id)
    if permissions is None:
        permissions = permission_service.effective_permissions(db, user)
    return {
        "id": user.id, "tenant_id": user.tenant_id, "name": user.name, "email": user.email,
        "role_code": user.role_code, "permissions": sorted(permissions),
    }


def authenticate_session(db: Session, token: str | None) -> Principal:
    """Turn a session cookie into a Principal, or raise NotAuthenticated."""
    if not token:
        raise NotAuthenticated("Not logged in.")
    session = db.scalars(select(UserSession).where(UserSession.token_hash == hash_token(token))).first()
    if session is None:
        raise NotAuthenticated("Not logged in.")

    check_session_alive(session)

    user = db.get(User, session.user_id)
    if not user.is_active:
        raise NotAuthenticated("This account is deactivated.", code="account_inactive")
    tenant = db.get(Tenant, user.tenant_id)
    if tenant.status != "active":
        raise NotAuthenticated("This lodge's account is suspended.", code="tenant_suspended")

    return Principal(
        kind="tenant", user_id=user.id, tenant_id=user.tenant_id, role_code=user.role_code,
        permissions=permission_service.effective_permissions(db, user), session_id=session.id,
    )
