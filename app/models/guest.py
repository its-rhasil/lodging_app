from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Guest(Base):
    __tablename__ = "guests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_guests_tenant_id_id"),
        # Repeat-guest lookup by phone at check-in (DL-P05).
        Index("ix_guests_tenant_phone", "tenant_id", "phone"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)  # normalised: digits, optional leading '+'
    email = Column(String)
    address = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    stays = relationship("Stay", back_populates="guest", viewonly=True)
