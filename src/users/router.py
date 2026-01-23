from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db, require_permission
from src.core.responses import PaginatedResponse
from src.users.schemas import UserCreate, UserOut
from src.users.service import (
    create_user_service,
    get_user_by_id_service,
    get_users_service,
)

user_router = APIRouter(prefix="/users", tags=["Users"])


@user_router.post("/root", response_model=UserOut, status_code=201)
async def create_root_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await create_user_service(db, user_in, is_root=True, tenant_id=None)
        user = result["user"]

        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Failed to create user")


@user_router.post("/", response_model=UserOut, status_code=201)
async def create_regular_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("users:create")),
):
    tenant_id = current_user["tenant_id"]

    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant ID is required")
    try:
        result = await create_user_service(
            db, user_in, is_root=False, tenant_id=tenant_id
        )
        user = result["user"]

        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Failed to create user")


@user_router.get("/{user_id}", response_model=UserOut, status_code=200)
async def get_user_by_id(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("users:read")),
):
    try:
        result = await get_user_by_id_service(user_id, db)
        user = result["user"]

        return user
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@user_router.get("/", response_model=PaginatedResponse, status_code=200)
async def get_users(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("users:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    tenant_id = current_user["tenant_id"]

    try:
        return await get_users_service(tenant_id, db, page, page_size)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
