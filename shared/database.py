"""
Huerto Connect — Database connections for microservices.
Provides MongoDB (Motor) and PostgreSQL (asyncpg/SQLAlchemy) connection helpers.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from shared.config import settings


# ===================== MONGODB =====================

_mongo_client: AsyncIOMotorClient | None = None


async def connect_mongodb() -> AsyncIOMotorDatabase:
    """Connect to MongoDB and return the database instance."""
    global _mongo_client
    _mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
    db = _mongo_client[settings.MONGO_DB]
    # Verify connection
    await db.command("ping")
    return db


async def close_mongodb():
    """Close MongoDB connection."""
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None


# ===================== POSTGRESQL =====================

class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all PostgreSQL models."""
    pass


def get_postgres_engine():
    """Create async SQLAlchemy engine for PostgreSQL."""
    async_uri = settings.POSTGRES_URI.replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    return create_async_engine(async_uri, echo=False)


def get_session_factory(engine):
    """Create async session factory."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_postgres_tables(engine):
    """Create all tables defined by SQLAlchemy models."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
