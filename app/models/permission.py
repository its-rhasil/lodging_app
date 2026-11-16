from sqlalchemy import Column, String

from app.database import Base


class Permission(Base):
    """Global permission catalogue keyed by code, e.g. 'folio.waive' (architecture.md §6.3)."""
    __tablename__ = "permissions"

    code = Column(String, primary_key=True)
    description = Column(String)
