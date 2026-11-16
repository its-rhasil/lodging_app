from sqlalchemy import Column, ForeignKey, String

from app.database import Base


class RolePermission(Base):
    """Default role -> permission mapping (DL-P18). Seeded by migration."""
    __tablename__ = "role_permissions"

    role_code = Column(String, ForeignKey("roles.code", ondelete="CASCADE"), primary_key=True)
    permission_code = Column(
        String, ForeignKey("permissions.code", ondelete="CASCADE"), primary_key=True
    )
