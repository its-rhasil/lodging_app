from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey,
    CheckConstraint, Index, Boolean
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
            CheckConstraint(
                "role IN ('owner', 'admin', 'receptionist')",
                name="ck_user_role",
            ),
    )
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    email = Column(String, nullable=False, unique= True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="users")
    sessions = relationship("UserSession", back_populates="user")

