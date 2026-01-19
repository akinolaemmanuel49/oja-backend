from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.users.schemas import UserCreate, UserOut
from src.users.service import create_user, read_user

users = APIRouter(prefix="/users")


@users.post("/root", response_model=UserOut, status_code=201)
async def create_new_root_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await create_user(db, user_in, is_root=True)
        return result["user"]
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@users.post("/", response_model=UserOut, status_code=201)
async def create_new_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    if user_in.tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant ID is required")
    try:
        result = await create_user(db, user_in, is_root=False)
        return result["user"]
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@users.get("/{user_id}", response_model=UserOut, status_code=200)
async def read_user_by_id(user_id: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await read_user(user_id, db)
        return result["user"]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
