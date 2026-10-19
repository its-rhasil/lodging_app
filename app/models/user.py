from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey,
    CheckConstraint, Index, Boolean, UniqueConstraint
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base

class TenantRole(Base):
    __tablename__ = "tenant_roles"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "name",
            name="uq_tenant_role_name",
        ),
    )

    id = Column(Integer, primary_key=True)

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id"),
        nullable=False,
    )

    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    tenant = relationship("Tenant", back_populates="custom_roles")
    users = relationship("User", back_populates="custom_role")
    permissions = relationship(
        "TenantRolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            """
            (
                system_role = 'superadmin'
                AND tenant_id IS NULL
                AND role_id IS NULL
            )
            OR
            (
                system_role = 'admin'
                AND tenant_id IS NOT NULL
                AND role_id IS NULL
            )
            OR
            (
                system_role IS NULL
                AND tenant_id IS NOT NULL
                AND role_id IS NOT NULL
            )
            """,
            name="ck_user_identity_scope",
        ),
    )
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    email = Column(String, nullable=False, unique= True)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role_id = Column(Integer, ForeignKey("tenant_roles.id"),nullable=True)
    system_role = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="users")
    sessions = relationship("UserSession", back_populates="user")
    custom_role = relationship("TenantRole", back_populates="users")

