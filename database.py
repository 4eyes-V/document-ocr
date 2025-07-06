from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import create_engine
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import os

class Base(DeclarativeBase):
    pass

# Асинхронный движок для FastAPI
async_engine = create_async_engine(os.getenv("DATABASE_URL"))
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    class_=AsyncSession
)

# Синхронный движок для Celery
sync_engine = create_engine(os.getenv("SYNC_DATABASE_URL"))
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False
)

# Корректный асинхронный контекстный менеджер для сессий
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

@asynccontextmanager
async def lifespan(app):
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await async_engine.dispose()