"""Database base — declarative base and async session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """Dependency — yields an async session, auto-closes on exit."""
    async with async_session_factory() as session:
        yield session


async def init_db():
    """Create all tables (for dev/SQLite). In production, use Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
