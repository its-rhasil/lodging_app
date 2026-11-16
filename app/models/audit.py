"""Audit trail (DL-R12). Append-only (DL-P13). Never store passwords, tokens or hashes."""
from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.sql import func

from app.database import Base

ACTOR_TYPES = ("tenant_user", "platform_user", "system", "anonymous")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('tenant_user', 'platform_user', 'system', 'anonymous')",
            name="ck_audit_actor_type",
        ),
        CheckConstraint(
            "((actor_type = 'tenant_user') = (actor_user_id IS NOT NULL))"
            " AND ((actor_type = 'platform_user') = (actor_platform_user_id IS NOT NULL))",
            name="ck_audit_actor_ids",
        ),
        Index("ix_audit_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_actor_created", "actor_user_id", "created_at"),
    )

    id = Column(BigInteger, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))  # NULL only for pure platform actions
    actor_type = Column(String, nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"))
    actor_platform_user_id = Column(Integer, ForeignKey("platform_users.id"))
    action = Column(String, nullable=False)  # dotted verb, e.g. 'auth.login.failed'
    entity_type = Column(String)
    entity_id = Column(String)
    summary = Column(String)
    changes = Column(JSONB)  # {"field": [before, after]}
    reason = Column(String)
    request_id = Column(String)
    ip = Column(INET)
    user_agent = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
