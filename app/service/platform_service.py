"""Platform superadmins: creation (CLI only), login, logout, sessions (DL-R04, DL-P07).

Same hardening as tenant login: dummy-hash timing, the same generic error,
audited outcomes. Platform events have tenant_id NULL.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotAuthenticated
from app.core.principal import ANONYMOUS, SYSTEM, Actor, Principal
from app.core.request_context import RequestMeta
from app.core.security import (
    dummy_password_hash, generate_token, get_token_expiry, hash_password, hash_token, utcnow,
    validate_email_address, validate_new_password, verify_password, normalize_email,
)
from app.models import PlatformSession, PlatformUser
from app.service import audit_service
from app.service.auth_service import INVALID_CREDENTIALS, check_session_alive


def create_superadmin(db: Session, *, email: str, name: str, password: str) -> PlatformUser:
    email = validate_email_address(email)
    validate_new_password(password)
    user = PlatformUser(email=email, name=name.strip(), hashed_password=hash_password(password))
    db.add(user)
    db.flush()  # uq_platform_users_email
    audit_service.record(
        db, action="platform_user.created", actor=SYSTEM, tenant_id=None,
        entity_type="platform_user", entity_id=user.id, summary=f"Created superadmin {email}",
    )
    db.commit()
    return user


def login(db: Session, *, email: str, password: str, meta: RequestMeta) -> tuple[str, PlatformUser]:
    email = normalize_email(email)
    user = db.scalars(select(PlatformUser).where(func.lower(PlatformUser.email) == email)).first()

    if user is None:
        verify_password(password, dummy_password_hash())
        _login_failed(db, meta, email, user=None, cause="unknown email")
    if not verify_password(password, user.hashed_password):
        _login_failed(db, meta, email, user=user, cause="wrong password")
    if not user.is_active:
        _login_failed(db, meta, email, user=user, cause="user deactivated",
                      code="account_inactive", message="This account is deactivated.")

    raw_token = generate_token()
    db.add(PlatformSession(platform_user_id=user.id, token_hash=hash_token(raw_token), expires_at=get_token_expiry()))
    user.last_login_at = utcnow()
    audit_service.record(
        db, action="platform.auth.login", actor=Actor.platform_user(user.id), tenant_id=None,
        entity_type="platform_user", entity_id=user.id, summary=f"{user.email} logged in", meta=meta,
    )
    db.commit()
    return raw_token, user


def _login_failed(db: Session, meta: RequestMeta, email: str, *, user: PlatformUser | None, cause: str,
                  code: str = "invalid_credentials", message: str = INVALID_CREDENTIALS) -> None:
    audit_service.record(
        db, action="platform.auth.login.failed", actor=ANONYMOUS, tenant_id=None,
        entity_type="platform_user" if user else None, entity_id=user.id if user else None,
        summary=f"Failed platform login for {email[:254]}: {cause}", meta=meta,
    )
    db.commit()
    raise NotAuthenticated(message, code=code)


def logout(db: Session, *, token: str | None, meta: RequestMeta) -> None:
    if not token:
        return
    session = db.scalars(
        select(PlatformSession)
        .where(PlatformSession.token_hash == hash_token(token), PlatformSession.revoked_at.is_(None))
    ).first()
    if session is None:
        return
    session.revoked_at = utcnow()
    audit_service.record(
        db, action="platform.auth.logout", actor=Actor.platform_user(session.platform_user_id), tenant_id=None,
        entity_type="platform_user", entity_id=session.platform_user_id, summary="Platform logout", meta=meta,
    )
    db.commit()


def authenticate_session(db: Session, token: str | None) -> Principal:
    if not token:
        raise NotAuthenticated("Not logged in.")
    session = db.scalars(select(PlatformSession).where(PlatformSession.token_hash == hash_token(token))).first()
    if session is None:
        raise NotAuthenticated("Not logged in.")
    check_session_alive(session)
    user = db.get(PlatformUser, session.platform_user_id)
    if not user.is_active:
        raise NotAuthenticated("This account is deactivated.", code="account_inactive")
    # Platform users hold no tenant permissions; platform routes check the principal kind.
    return Principal(kind="platform", user_id=user.id, tenant_id=None, role_code=None,
                     permissions=frozenset(), session_id=session.id)


def profile(db: Session, platform_user_id: int) -> dict:
    user = db.get(PlatformUser, platform_user_id)
    return {"id": user.id, "email": user.email, "name": user.name}
