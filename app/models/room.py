from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Integer,
    Numeric, String, UniqueConstraint, text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# Relationships over composite (tenant_id, x_id) keys are viewonly: services set the
# id columns explicitly, and several relationships share tenant_id, so letting the ORM
# write through them would make it copy tenant_id from more than one parent.


class RoomType(Base):
    __tablename__ = "room_types"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_room_type_name_per_tenant"),
        UniqueConstraint("tenant_id", "id", name="uq_room_types_tenant_id_id"),
        CheckConstraint("capacity > 0", name="ck_room_type_capacity"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    capacity = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rooms = relationship("Room", back_populates="room_type", viewonly=True)
    rates = relationship("RoomTypeRate", viewonly=True, order_by="RoomTypeRate.occupancy")


class RoomTypeRate(Base):
    """Price per period of a stay plan, per occupancy (replaces room_type_prices)."""
    __tablename__ = "room_type_rates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "room_type_id"], ["room_types.tenant_id", "room_types.id"],
            name="fk_room_type_rates_room_type", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "stay_plan_id"], ["stay_plans.tenant_id", "stay_plans.id"],
            name="fk_room_type_rates_stay_plan",
        ),
        UniqueConstraint("room_type_id", "stay_plan_id", "occupancy", name="uq_rate"),
        CheckConstraint("occupancy > 0", name="ck_rate_occupancy"),
        CheckConstraint("price > 0", name="ck_rate_price"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False)
    room_type_id = Column(Integer, nullable=False)
    stay_plan_id = Column(Integer, nullable=False)
    occupancy = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("tenant_id", "room_number", name="uq_room_number_per_tenant"),
        UniqueConstraint("tenant_id", "id", name="uq_rooms_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "room_type_id"], ["room_types.tenant_id", "room_types.id"],
            name="fk_rooms_room_type",
        ),
        CheckConstraint(
            "operational_status IN ('available', 'cleaning', 'maintenance')",
            name="ck_room_operational_status",
        ),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    room_type_id = Column(Integer, nullable=False)
    room_number = Column(String(20), nullable=False)  # string: '101', 'A-12' (D-27)
    operational_status = Column(
        String, nullable=False, default="available", server_default="available"
    )
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    room_type = relationship("RoomType", back_populates="rooms", viewonly=True)
