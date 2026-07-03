import os
from datetime import timezone
from sqlalchemy import create_engine, DateTime, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///memorizer.db")

class UTCDateTime(TypeDecorator):
    """DateTime that stores UTC and always returns timezone-aware values.

    SQLite's DateTime(timezone=True) returns naive datetimes on read; this
    normalizes to UTC on write and re-attaches tzinfo=UTC on read.
    """
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

class Base(DeclarativeBase):
    pass

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from app import models  # noqa: F401  (register models)
    Base.metadata.create_all(engine)
