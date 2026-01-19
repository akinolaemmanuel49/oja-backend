from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.database.session import AsyncSessionLocal


def get_app_settings() -> Settings:
    return get_settings()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to provide a database session per request"""
    async with AsyncSessionLocal() as session:
        yield session
