from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, ForeignKey,
    CheckConstraint, Index
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Stay(Base):
    __tablename__ = "stays"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'checked_out', 'cancelled')",
            name="ck_stay_status",
        ),
        # the no-double-booking rule, enforced by the database itself:
        # only one row per room can be 'active' at a time
        Index(
            "uq_one_active_stay_per_room", "room_id",
            unique=True, postgresql_where=(Column("status") == "active"),
        ),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    guest_id = Column(Integer, ForeignKey("guests.id"), nullable=False)
    status = Column(String, nullable=False, default="active")
    planned_check_in_at = Column(DateTime(timezone=True))
    actual_check_in_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expected_checkout_at = Column(DateTime(timezone=True), nullable=False)
    actual_checkout_at = Column(DateTime(timezone=True), nullable=True)
    agreed_price = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("Room", back_populates="stays")
    guest = relationship("Guest", back_populates="stays")
    payments = relationship("Payment", back_populates="stay")