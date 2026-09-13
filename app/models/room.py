from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, ForeignKey,
    CheckConstraint, UniqueConstraint
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, ForeignKey,
    UniqueConstraint
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class RoomType(Base):
    __tablename__ = "room_types"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "name",
            name="uq_room_type_name_per_tenant"
        ),
    )

    id = Column(Integer, primary_key=True)

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )

    name = Column(String, nullable=False)
    description = Column(String)
    default_price = Column(Numeric(10, 2), nullable=False)
    capacity = Column(Integer, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    tenant = relationship("Tenant", back_populates="room_types")
    rooms = relationship("Room", back_populates="room_type")


class Room(Base):
    __tablename__ = "rooms"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "room_number",
            name="uq_room_number_per_tenant"
        ),
        CheckConstraint(
            "operational_status IN ('available', 'cleaning', 'maintenance')",
            name="ck_room_operational_status",
        ),
    )

    id = Column(Integer, primary_key=True)

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )

    room_type_id = Column(
        Integer,
        ForeignKey("room_types.id"),
        nullable=False
    )

    room_number = Column(String, nullable=False)

    operational_status = Column(
        String,
        nullable=False,
        default="available"
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    tenant = relationship("Tenant", back_populates="rooms")
    room_type = relationship("RoomType", back_populates="rooms")
    stays = relationship("Stay", back_populates="room")