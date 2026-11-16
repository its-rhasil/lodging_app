from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String,
    UniqueConstraint, func, text,
)

from app.database import Base


class StayPlan(Base):
    """A product the tenant sells: 'Full day' (24h), 'Fresh-up' (e.g. 3h), 'Hourly' (DL-R17)."""
    __tablename__ = "stay_plans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_stay_plans_tenant_id_id"),
        CheckConstraint("period_hours BETWEEN 1 AND 24", name="ck_stay_plan_period_hours"),
        CheckConstraint("grace_minutes BETWEEN 0 AND 240", name="ck_stay_plan_grace_minutes"),
        # The daily plan is always 24h and can't be deactivated.
        CheckConstraint("NOT is_daily OR (period_hours = 24 AND is_active)", name="ck_daily_plan"),
        Index("uq_one_daily_plan", "tenant_id", unique=True, postgresql_where=text("is_daily")),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    period_hours = Column(Integer, nullable=False)
    grace_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    is_daily = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Plans are never deleted once used; they are deactivated.
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


Index("uq_stay_plan_name", StayPlan.tenant_id, func.lower(StayPlan.name), unique=True)
