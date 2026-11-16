"""Platform principals (superadmin). Separate from tenant users (DL-R04, DL-P07)."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import relationship

from app.database import Base


class PlatformUser(Base):
    __tablename__ = "platform_users"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)  # stored lowercase
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_login_at = Column(DateTime(timezone=True))

    sessions = relationship("PlatformSession", back_populates="platform_user")


Index("uq_platform_users_email", func.lower(PlatformUser.email), unique=True)


class PlatformSession(Base):
    __tablename__ = "platform_sessions"

    id = Column(Integer, primary_key=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    platform_user_id = Column(Integer, ForeignKey("platform_users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))

    platform_user = relationship("PlatformUser", back_populates="sessions")
