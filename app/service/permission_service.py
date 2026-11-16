"""Effective permissions (architecture.md §6.4): role ∪ grants − denies. Deny wins."""
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RolePermission, User, UserPermissionOverride


def combine(role_permissions: Iterable[str], overrides: Iterable[tuple[str, str]]) -> frozenset[str]:
    """overrides: (permission_code, effect) pairs, effect 'grant' or 'deny'."""
    overrides = list(overrides)  # read twice below; a generator would be empty the second time
    grants = {code for code, effect in overrides if effect == "grant"}
    denies = {code for code, effect in overrides if effect == "deny"}
    return frozenset((set(role_permissions) | grants) - denies)


def role_permissions(db: Session, role_code: str) -> set[str]:
    return set(db.scalars(
        select(RolePermission.permission_code).where(RolePermission.role_code == role_code)
    ))


def user_overrides(db: Session, user: User) -> list[UserPermissionOverride]:
    return list(db.scalars(
        select(UserPermissionOverride)
        .where(UserPermissionOverride.tenant_id == user.tenant_id, UserPermissionOverride.user_id == user.id)
        .order_by(UserPermissionOverride.permission_code)
    ))


def effective_permissions(db: Session, user: User) -> frozenset[str]:
    overrides = [(o.permission_code, o.effect) for o in user_overrides(db, user)]
    return combine(role_permissions(db, user.role_code), overrides)
