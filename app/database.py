from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,  # replace connections the pooler closed while idle
    pool_size=5,
    max_overflow=5,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

def get_db():
    """One session per request (unit of work).

    The service commits once at the end of a use case. If anything raises
    before that, the session is rolled back here, so a half-done change
    (or an audit row without its change) never reaches the database.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
