from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database.engine import engine

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
