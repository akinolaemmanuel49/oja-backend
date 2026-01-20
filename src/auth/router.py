from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Login
from src.auth.service import login_service
from src.core.dependencies import get_current_user, get_db
from src.core.session import create_session, destroy_session
from src.users.schemas import UserOut
from src.users.service import get_user_by_id_service

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


@auth_router.post("/login")
async def login(
    login_data: Login,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    user = await login_service(db, login_data.email, login_data.password)

    await create_session(db, str(user["id"]), request, response)
    return {"message": "Logged in successfully"}


@auth_router.post("/logout")
async def logout(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    await destroy_session(db, request, response)
    return {"message": "Logged out"}


@auth_router.get("/me", response_model=UserOut)
async def me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user_id = current_user["user_id"]
    result = await get_user_by_id_service(current_user_id, db)
    return result["user"]
