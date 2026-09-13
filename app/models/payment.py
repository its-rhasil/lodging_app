from sqlalchemy import Column, Integer, Numeric, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    stay_id = Column(Integer, ForeignKey("stays.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(String, nullable=False)   # 'cash' | 'card' | 'upi' etc — plain string, not enum
    paid_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    stay = relationship("Stay", back_populates="payments")