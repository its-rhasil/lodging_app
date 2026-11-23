"""Stay plans (DL-R17, P4-2): the products a tenant sells (Full day, Fresh-up, Hourly, ...).

Rules:
- the daily plan is created by create-tenant; the API never creates another one;
- the daily plan stays 24h and active (ck_daily_plan; checked here first for a clear 422);
- plans are never deleted, only deactivated (stays and rates point at them);
- editing a plan never changes a current stay's bill: stays copy period and grace at check-in.
"""
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.principal import Principal
from app.core.request_context import RequestMeta
from app.models import RoomTypeRate, Stay, StayPlan
from app.service import audit_service

EDITABLE_FIELDS = ("name", "period_hours", "grace_minutes", "is_active", "sort_order")


def list_plans(db: Session, principal: Principal) -> list[StayPlan]:
    return list(db.scalars(
        select(StayPlan)
        .where(StayPlan.tenant_id == principal.tenant_id)
        .order_by(StayPlan.sort_order, StayPlan.id)
    ))


def get_plan(db: Session, tenant_id: int, plan_id: int, *, lock: bool = False) -> StayPlan:
    """A plan of this tenant. Another tenant's plan is reported as not found."""
    query = select(StayPlan).where(StayPlan.tenant_id == tenant_id, StayPlan.id == plan_id)
    if lock:
        query = query.with_for_update()
    plan = db.scalars(query).first()
    if plan is None:
        raise NotFound("Stay plan not found.", code="stay_plan_not_found")
    return plan


def create_plan(db: Session, principal: Principal, *, name: str, period_hours: int,
                grace_minutes: int, sort_order: int, meta: RequestMeta) -> StayPlan:
    plan = StayPlan(
        tenant_id=principal.tenant_id, name=name.strip(), period_hours=period_hours,
        grace_minutes=grace_minutes, sort_order=sort_order, is_daily=False, is_active=True,
    )
    db.add(plan)
    db.flush()  # a taken name fails here: uq_stay_plan_name -> 409 stay_plan_name_taken
    audit_service.record(
        db, action="stay_plan.created", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="stay_plan", entity_id=plan.id, summary=f"Stay plan: {plan.name} · Created",
        changes={"name": [None, plan.name], "period_hours": [None, period_hours],
                 "grace_minutes": [None, grace_minutes]},
        meta=meta,
    )
    db.commit()
    return plan


def update_plan(db: Session, principal: Principal, plan_id: int, fields: dict, *,
                meta: RequestMeta) -> StayPlan:
    """`fields` holds only what the client sent (exclude_unset)."""
    plan = get_plan(db, principal.tenant_id, plan_id, lock=True)
    if "name" in fields and fields["name"] is not None:
        fields["name"] = fields["name"].strip()
    # None means "not sent" for every field here; none of them can be cleared.
    fields = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS and v is not None}

    if plan.is_daily:
        if fields.get("period_hours", 24) != 24:
            raise ValidationFailed("The daily plan is always 24 hours.", code="daily_plan_period_fixed")
        if fields.get("is_active", True) is False:
            raise ValidationFailed("The daily plan can't be deactivated.", code="daily_plan_always_active")

    changes = {k: [getattr(plan, k), v] for k, v in fields.items() if getattr(plan, k) != v}
    if not changes:
        return plan
    for key, (_, new) in changes.items():
        setattr(plan, key, new)
    db.flush()  # uq_stay_plan_name on a rename
    audit_service.record(
        db, action="stay_plan.updated", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="stay_plan", entity_id=plan.id, summary=f"Stay plan: {plan.name} · Updated",
        changes=changes, meta=meta,
    )
    db.commit()
    return plan


def delete_plan(db: Session, principal: Principal, plan_id: int, *, meta: RequestMeta) -> None:
    """Delete a plan that no stay has ever used (DL-R17: a used plan can only be deactivated).
    Its rates go with it, so room types simply stop offering it."""
    plan = get_plan(db, principal.tenant_id, plan_id, lock=True)
    if plan.is_daily:
        raise ValidationFailed("The daily plan can't be deleted.", code="daily_plan_required")
    used = db.scalar(
        select(Stay.id)
        .where(Stay.tenant_id == principal.tenant_id,
               or_(Stay.stay_plan_id == plan.id, Stay.converted_from_plan_id == plan.id))
        .limit(1)
    )
    if used is not None:
        raise Conflict("Guests have stayed on this plan, so it can't be deleted. Deactivate it instead.",
                       code="stay_plan_in_use")

    removed_rates = db.execute(delete(RoomTypeRate).where(RoomTypeRate.stay_plan_id == plan.id)).rowcount
    audit_service.record(
        db, action="stay_plan.deleted", actor=principal.actor, tenant_id=principal.tenant_id,
        entity_type="stay_plan", entity_id=plan.id, summary=f"Stay plan: {plan.name} · Deleted",
        changes={"name": [plan.name, None], "rates_removed": [removed_rates, None]}, meta=meta,
    )
    db.delete(plan)
    db.commit()
