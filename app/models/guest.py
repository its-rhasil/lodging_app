from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Guest(Base):
    __tablename__ = "guests"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String)
    address = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now(),nullable=False)

    stays = relationship("Stay", back_populates="guest")