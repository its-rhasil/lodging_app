from sqlalchemy import CHAR, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Time
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended')", name="ck_tenant_status"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    contact_email = Column(String, nullable=False)
    contact_phone = Column(String, nullable=False)
    address = Column(String)
    # A suspended tenant's logins are rejected.
    status = Column(String, nullable=False, default="active", server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    settings = relationship("TenantSettings", uselist=False, back_populates="tenant")


class TenantSettings(Base):
    """1:1 with tenants. India values are only the defaults (DL-P17)."""
    __tablename__ = "tenant_settings"
    __table_args__ = (
        CheckConstraint(
            "billing_mode IN ('rolling_24h', 'fixed_checkout')", name="ck_tenant_settings_billing_mode"
        ),
        CheckConstraint("max_backdate_minutes >= 0", name="ck_tenant_settings_max_backdate"),
    )

    tenant_id = Column(Integer, ForeignKey("tenants.id"), primary_key=True)
    timezone = Column(String, nullable=False, default="Asia/Kolkata", server_default="Asia/Kolkata")
    currency = Column(CHAR(3), nullable=False, default="INR", server_default="INR")
    # Only rolling_24h is implemented in the beta.
    billing_mode = Column(String, nullable=False, default="rolling_24h", server_default="rolling_24h")
    checkout_time = Column(Time)  # used only by fixed_checkout (post-beta)
    max_backdate_minutes = Column(Integer, nullable=False, default=120, server_default="120")
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tenant = relationship("Tenant", back_populates="settings")
