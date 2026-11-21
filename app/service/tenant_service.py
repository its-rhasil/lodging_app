"""Tenant onboarding (DL-R03). Beta: called by the create-tenant CLI only; no public signup."""
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.principal import SYSTEM, Actor
from app.core.security import hash_password, validate_email_address, validate_new_password
from app.core.errors import ValidationFailed
from app.models import StayPlan, Tenant, TenantSettings, User
from app.service import audit_service

# The one plan every tenant starts with (data-model.md §4.3). Others are added by the tenant admin.
DAILY_PLAN = {"name": "Full day", "period_hours": 24, "grace_minutes": 30, "is_daily": True}


def _required(value: str, field: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValidationFailed(f"{field} is required.", code="field_required", details={"field": field})
    return value


def create_tenant(db: Session, *, name: str, contact_email: str, contact_phone: str, address: str | None,
                  admin_email: str, admin_name: str, admin_password: str,
                  actor: Actor = SYSTEM) -> tuple[Tenant, User]:
    """Tenant + settings (defaults) + daily plan + its tenant admin, in one commit."""
    name = _required(name, "name")
    contact_phone = _required(contact_phone, "contact_phone")
    admin_name = _required(admin_name, "admin_name")
    contact_email = validate_email_address(contact_email)
    admin_email = validate_email_address(admin_email)
    validate_new_password(admin_password)

    tenant = Tenant(name=name, contact_email=contact_email, contact_phone=contact_phone,
                    address=(address or "").strip() or None)
    db.add(tenant)
    db.flush()
    db.add(TenantSettings(tenant_id=tenant.id))
    db.add(StayPlan(tenant_id=tenant.id, **DAILY_PLAN))
    admin = User(tenant_id=tenant.id, email=admin_email, name=admin_name,
                 hashed_password=hash_password(admin_password), role_code="tenant_admin")
    db.add(admin)
    db.flush()  # uq_users_email fires here if the admin email is taken

    audit_service.record(
        db, action="tenant.created", actor=actor, tenant_id=tenant.id,
        entity_type="tenant", entity_id=tenant.id, summary=f"Created tenant {name}",
    )
    audit_service.record(
        db, action="user.created", actor=actor, tenant_id=tenant.id,
        entity_type="user", entity_id=admin.id, summary=f"Created tenant_admin {admin_email}",
        changes={"email": [None, admin_email], "role_code": [None, "tenant_admin"]},
    )
    db.commit()
    return tenant, admin


# --- tenant settings (Day 3) ----------------------------------------------------------

def get_settings(db: Session, tenant_id: int) -> TenantSettings:
    return db.get(TenantSettings, tenant_id)


def update_settings(db: Session, principal, fields: dict, *, meta) -> TenantSettings:
    """Timezone, currency, backdate window. Only the fields sent are changed."""
    settings = db.scalars(
        select(TenantSettings).where(TenantSettings.tenant_id == principal.tenant_id).with_for_update()
    ).one()
    fields = {k: v for k, v in fields.items() if v is not None}
    if "currency" in fields:
        fields["currency"] = fields["currency"].upper()
    if "timezone" in fields:
        # PostgreSQL's own list: no timezone package needed in Python.
        known = db.scalar(text("SELECT count(*) FROM pg_timezone_names WHERE name = :tz"),
                          {"tz": fields["timezone"]})
        if not known:
            raise ValidationFailed("Unknown timezone.", code="unknown_timezone")

    changes = {k: [getattr(settings, k), v] for k, v in fields.items() if getattr(settings, k) != v}
    if not changes:
        return settings
    for key, (_, new) in changes.items():
        setattr(settings, key, new)
    audit_service.record(
        db, action="settings.updated", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="tenant_settings", entity_id=principal.tenant_id, summary="Updated tenant settings",
        changes=changes, meta=meta,
    )
    db.commit()
    return settings
