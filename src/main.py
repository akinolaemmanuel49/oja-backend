from contextlib import asynccontextmanager

from asyncpg.exceptions import ForeignKeyViolationError, UniqueViolationError
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.auth.router import auth_router
from src.core.config import settings
from src.core.dependencies import get_db
from src.database.engine import engine
from src.groups.router import group_router
from src.permissions.router import permissions_router
from src.products.router import products_router
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
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
        500: {"description": "Internal server error"},
    },
)

origins = settings.ALLOWED_ORIGINS

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom exception handler
@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, exc: IntegrityError):
    original_exc = exc.orig
    if isinstance(original_exc, ForeignKeyViolationError):
        detail = "Resource not found"
        if "user_permissions_user_id_fkey" in str(original_exc):
            detail = "User or permission does not exist"
    elif isinstance(original_exc, UniqueViolationError):
        detail = "Resource already exists"
        if "users_email_key" in str(original_exc):
            detail = "Email address already registered"
        elif "storefronts_slug_key" in str(original_exc):
            detail = "Storefront slug already taken"
        elif "storefronts_tenant_id_name_key" in str(original_exc):
            detail = "Storefront name already taken"

        return JSONResponse(status_code=409, content={"detail": detail})

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    if "Invalid credentials" in str(exc):
        return JSONResponse(status_code=401, content={"detail": "Invalid credentials"})
    elif "User is deleted" in str(exc):
        return JSONResponse(status_code=404, content={"detail": "User not found"})
    return JSONResponse(status_code=400, content={"detail": "Bad request"})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers if exc.headers else {},
    )


@app.exception_handler(Exception)
async def general_exception_handler(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Register routes
# Auth routes
app.include_router(auth_router, dependencies=[Depends(get_db)])
# User routes
app.include_router(user_router, dependencies=[Depends(get_db)])
# Permissions routes
app.include_router(permissions_router, dependencies=[Depends(get_db)])
# Storefront routes
app.include_router(storefront_router, dependencies=[Depends(get_db)])
# Product routes
app.include_router(products_router, dependencies=[Depends(get_db)])
# Group routes
app.include_router(group_router, dependencies=[Depends(get_db)])


@app.get("/health")
async def health_check():
    return {"status": "ok"}
