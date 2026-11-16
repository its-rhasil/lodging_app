"""Tenant user administration (P1-3, P3-3). Every function needs user.manage (checked by the route).

Guardrails (architecture.md §6.4, DL-R05):
- only manager/receptionist can be created; tenant_admin comes from the platform;
- the tenant admin can't be deactivated or given overrides by tenant users;
- nobody deactivates themselves or edits their own overrides;
- a grant is limited to permissions the person granting it holds.
"""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.core.principal import Principal
from app.core.request_context import RequestMeta
from app.core.security import hash_password, normalize_email, utcnow, validate_new_password
from app.models import Permission, User, UserPermissionOverride, UserSession
from app.service import audit_service, permission_service

ASSIGNABLE_ROLES = ("manager", "receptionist")
TENANT_ADMIN = "tenant_admin"


def _get_user(db: Session, principal: Principal, user_id: int, *, lock: bool = False) -> User:
    """A user of the caller's tenant. Another tenant's user is reported as not found."""
    query = select(User).where(User.tenant_id == principal.tenant_id, User.id == user_id)
    if lock:
        query = query.with_for_update()
    user = db.scalars(query).first()
    if user is None:
        raise NotFound("User not found.", code="user_not_found")
    return user


def list_users(db: Session, principal: Principal) -> list[User]:
    return list(db.scalars(
        select(User).where(User.tenant_id == principal.tenant_id).order_by(User.name, User.id)
    ))


def get_user_detail(db: Session, principal: Principal, user_id: int) -> dict:
    return _detail(db, _get_user(db, principal, user_id))


def _detail(db: Session, user: User) -> dict:
    overrides = permission_service.user_overrides(db, user)
    return {
        "id": user.id, "email": user.email, "name": user.name, "role_code": user.role_code,
        "is_active": user.is_active, "created_at": user.created_at,
        "overrides": overrides,
        "permissions": sorted(permission_service.effective_permissions(db, user)),
    }


def create_user(db: Session, principal: Principal, *, email: str, name: str, password: str,
                role_code: str, meta: RequestMeta) -> User:
    if role_code not in ASSIGNABLE_ROLES:
        raise PermissionDenied("Only managers and receptionists can be created here.", code="role_not_assignable")
    validate_new_password(password)
    user = User(
        tenant_id=principal.tenant_id, email=normalize_email(email), name=name.strip(),
        hashed_password=hash_password(password), role_code=role_code,
    )
    db.add(user)
    db.flush()  # a taken email fails here: uq_users_email -> 409 email_taken
    audit_service.record(
        db, action="user.created", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="user", entity_id=user.id, summary=f"Created {role_code} {user.email}",
        changes={"email": [None, user.email], "role_code": [None, role_code]}, meta=meta,
    )
    db.commit()
    return user


def deactivate_user(db: Session, principal: Principal, user_id: int, *, meta: RequestMeta) -> User:
    user = _get_user(db, principal, user_id, lock=True)
    if user.id == principal.user_id:
        raise ValidationFailed("You can't deactivate your own account.", code="cannot_deactivate_self")
    if user.role_code == TENANT_ADMIN:
        raise PermissionDenied("The tenant admin can't be deactivated.", code="cannot_deactivate_tenant_admin")
    if not user.is_active:
        return user  # already done; nothing to audit

    now = utcnow()
    user.is_active = False
    # Log them out everywhere, now (not at their next request).
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    audit_service.record(
        db, action="user.deactivated", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="user", entity_id=user.id, summary=f"Deactivated {user.email}",
        changes={"is_active": [True, False]}, meta=meta,
    )
    db.commit()
    return user


def set_overrides(db: Session, principal: Principal, user_id: int, overrides: list[dict], *,
                  meta: RequestMeta) -> dict:
    """Replace the user's overrides with `overrides` (dicts: permission_code, effect, reason)."""
    user = _get_user(db, principal, user_id, lock=True)
    if user.id == principal.user_id:
        raise PermissionDenied("You can't change your own permissions.", code="cannot_override_self")
    if user.role_code == TENANT_ADMIN:
        raise PermissionDenied("The tenant admin's permissions can't be changed.",
                               code="cannot_override_tenant_admin")

    codes = [o["permission_code"] for o in overrides]
    duplicates = sorted({c for c in codes if codes.count(c) > 1})
    if duplicates:
        raise ValidationFailed("Each permission can appear only once.", code="duplicate_permission",
                               details={"permissions": duplicates})
    known = set(db.scalars(select(Permission.code).where(Permission.code.in_(codes)))) if codes else set()
    unknown = sorted(set(codes) - known)
    if unknown:
        raise ValidationFailed("Unknown permission.", code="unknown_permission", details={"permissions": unknown})
    unheld = sorted(o["permission_code"] for o in overrides
                    if o["effect"] == "grant" and not principal.has(o["permission_code"]))
    if unheld:
        raise PermissionDenied("You can only grant permissions you hold yourself.", code="cannot_grant_unheld",
                               details={"permissions": unheld})

    existing = permission_service.user_overrides(db, user)
    before = sorted(f"{o.effect}:{o.permission_code}" for o in existing)
    for row in existing:
        db.delete(row)
    db.flush()
    for o in overrides:
        db.add(UserPermissionOverride(
            tenant_id=user.tenant_id, user_id=user.id, permission_code=o["permission_code"],
            effect=o["effect"], reason=(o.get("reason") or "").strip() or None,
            created_by_user_id=principal.user_id,
        ))
    db.flush()
    after = sorted(f"{o['effect']}:{o['permission_code']}" for o in overrides)
    if before != after:
        audit_service.record(
            db, action="user.permissions.updated", actor=principal.actor, tenant_id=principal.tenant_id,
            entity_type="user", entity_id=user.id, summary=f"Changed permission overrides of {user.email}",
            changes={"overrides": [before, after]}, meta=meta,
        )
    db.commit()
    return _detail(db, user)
