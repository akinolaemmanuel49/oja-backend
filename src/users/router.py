from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db, require_permission
from src.users.schemas import UserCreate, UserOut
from src.users.service import create_user, read_user

user_router = APIRouter(prefix="/users")


@user_router.post("/root", response_model=UserOut, status_code=201)
async def create_new_root_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await create_user(db, user_in, is_root=True)
        return result["user"]
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@user_router.post("/", response_model=UserOut, status_code=201)
async def create_new_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("users:create")),
):
    tenant_id = current_user["tenant_id"]
    user_in.tenant_id = tenant_id

    if user_in.tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant ID is required")
    try:
        result = await create_user(db, user_in, is_root=False)
        return result["user"]
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@user_router.get("/{user_id}", response_model=UserOut, status_code=200)
async def read_user_by_id(user_id: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await read_user(user_id, db)
        return result["user"]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
