from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Target of composite (tenant_id, user_id) foreign keys.
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
        # Exactly one tenant admin per tenant (DL-R05).
        Index(
            "uq_one_tenant_admin", "tenant_id",
            unique=True, postgresql_where=text("role_code = 'tenant_admin'"),
        ),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    email = Column(String, nullable=False)  # stored lowercase; globally unique (DL-P06)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role_code = Column(String, ForeignKey("roles.code"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tenant = relationship("Tenant")
    sessions = relationship("UserSession", back_populates="user")


Index("uq_users_email", func.lower(User.email), unique=True)
