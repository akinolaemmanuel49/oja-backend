from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text

from src.auth.router import auth_router
from src.core.dependencies import get_db
from src.database.engine import engine
from src.permissions.router import permissions_router
from src.storefronts.router import storefront_router
from src.users.router import user_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await engine.dispose()


app = FastAPI(
    title="Oja Backend",
    description="Oja Backend API",
    version="0.1.0",
    contact={
        "name": "Oja Backend Team",
        "email": "biteatertest+oja-backend@gmail.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
)


# Register routes
# User routes
app.include_router(user_router, dependencies=[Depends(get_db)])
# Auth routes
app.include_router(auth_router, dependencies=[Depends(get_db)])
# Permissions routes
app.include_router(permissions_router, dependencies=[Depends(get_db)])
# Storefront routes
app.include_router(storefront_router, dependencies=[Depends(get_db)])


@app.get("/health")
async def health_check():
    return {"status": "ok"}
