from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Provide the declarative base shared by all database models."""

    pass


def get_database_session() -> Generator[Session, None, None]:
    """Provide one SQLAlchemy session and close it after use.

    Yields:
        A database session scoped to the current dependency use.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
