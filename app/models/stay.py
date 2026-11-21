from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer,
    Numeric, String, UniqueConstraint, text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Stay(Base):
    __tablename__ = "stays"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_stays_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "room_id"], ["rooms.tenant_id", "rooms.id"], name="fk_stays_room"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "guest_id"], ["guests.tenant_id", "guests.id"], name="fk_stays_guest"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "stay_plan_id"], ["stay_plans.tenant_id", "stay_plans.id"],
            name="fk_stays_stay_plan",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "converted_from_plan_id"], ["stay_plans.tenant_id", "stay_plans.id"],
            name="fk_stays_converted_from_plan",
        ),
        CheckConstraint("status IN ('active', 'checked_out', 'cancelled')", name="ck_stay_status"),
        CheckConstraint("occupancy > 0", name="ck_stay_occupancy"),
        CheckConstraint("agreed_price > 0", name="ck_stay_price"),
        CheckConstraint("listed_price > 0", name="ck_stay_listed_price"),
        # Discounts only: the agreed price never exceeds the rate-table price (owner, 2026-11-16).
        CheckConstraint("agreed_price <= listed_price", name="ck_stay_price_le_listed"),
        CheckConstraint(
            "actual_checkout_at IS NULL OR actual_checkout_at >= actual_check_in_at",
            name="ck_stay_dates",
        ),
        # No double booking: one active stay per room, enforced by the DB (DL-E03).
        Index(
            "uq_one_active_stay_per_room", "room_id",
            unique=True, postgresql_where=text("status = 'active'"),
        ),
        Index("ix_stays_tenant_status", "tenant_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    room_id = Column(Integer, nullable=False)
    guest_id = Column(Integer, nullable=False)
    stay_plan_id = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="active", server_default="active")
    # Set by the service from the injected clock (no DB default on purpose).
    actual_check_in_at = Column(DateTime(timezone=True), nullable=False)
    expected_checkout_at = Column(DateTime(timezone=True))
    actual_checkout_at = Column(DateTime(timezone=True))
    agreed_price = Column(Numeric(10, 2), nullable=False)  # current rate per period (after discount)
    # Rate-table price per period at check-in, kept so the discount % stays right after rates change.
    listed_price = Column(Numeric(10, 2), nullable=False)
    occupancy = Column(Integer, nullable=False)
    # Plan snapshot copied at check-in (and on conversion): editing the plan never rebills a stay.
    period_hours = Column(Integer, nullable=False)
    grace_minutes = Column(Integer, nullable=False)
    converted_at = Column(DateTime(timezone=True))
    converted_from_plan_id = Column(Integer)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    room = relationship("Room", viewonly=True)
    guest = relationship("Guest", back_populates="stays", viewonly=True)
    stay_plan = relationship(
        "StayPlan", viewonly=True,
        primaryjoin="and_(Stay.tenant_id == StayPlan.tenant_id, Stay.stay_plan_id == StayPlan.id)",
        foreign_keys="[Stay.tenant_id, Stay.stay_plan_id]",
    )
    folio = relationship("Folio", back_populates="stay", uselist=False, viewonly=True)


class StayRoomMove(Base):
    """Room change in place (DL-R13): the stay keeps its folio; the move is recorded here."""
    __tablename__ = "stay_room_moves"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "stay_id"], ["stays.tenant_id", "stays.id"], name="fk_stay_room_moves_stay"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "from_room_id"], ["rooms.tenant_id", "rooms.id"],
            name="fk_stay_room_moves_from_room",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "to_room_id"], ["rooms.tenant_id", "rooms.id"],
            name="fk_stay_room_moves_to_room",
        ),
        CheckConstraint("from_room_id <> to_room_id", name="ck_move_rooms_differ"),
        CheckConstraint("rate_before > 0", name="ck_move_rate_before"),
        CheckConstraint("rate_after > 0", name="ck_move_rate_after"),
        Index("ix_stay_room_moves_stay_moved_at", "stay_id", "moved_at"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False)
    stay_id = Column(Integer, nullable=False)
    from_room_id = Column(Integer, nullable=False)
    to_room_id = Column(Integer, nullable=False)
    rate_before = Column(Numeric(10, 2), nullable=False)
    rate_after = Column(Numeric(10, 2), nullable=False)
    moved_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    moved_by_user_id = Column(Integer, ForeignKey("users.id"))
    reason = Column(String)
