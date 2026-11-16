from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, func

from app.database import Base


class UserPermissionOverride(Base):
    """Per-user grant/deny on top of the role. Effective = role ∪ grants − denies (deny wins)."""
    __tablename__ = "user_permission_overrides"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_user_permission_overrides_user",
            ondelete="CASCADE",
        ),
        CheckConstraint("effect IN ('grant', 'deny')", name="ck_override_effect"),
    )

    tenant_id = Column(Integer, nullable=False)
    user_id = Column(Integer, primary_key=True)
    permission_code = Column(String, ForeignKey("permissions.code"), primary_key=True)
    effect = Column(String, nullable=False)
    reason = Column(String)
    created_by_user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
