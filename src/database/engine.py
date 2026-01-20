from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import settings

engine = create_async_engine(
    str(settings.DATABASE_URL),
    # echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
)
