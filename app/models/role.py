from sqlalchemy import Column, String

from app.database import Base


class Role(Base):
    """Global, predefined roles keyed by code (DL-R05, DL-P04). Seeded by migration."""
    __tablename__ = "roles"

    code = Column(String, primary_key=True)  # 'tenant_admin' | 'manager' | 'receptionist'
    name = Column(String, nullable=False)
    description = Column(String)
