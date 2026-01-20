from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Login
from src.core.dependencies import get_current_user, get_db
from src.core.security import verify_password
from src.core.session import create_session, destroy_session
from src.users.schemas import UserOut
from src.users.service import read_user

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

GET_USER_QUERY = text("""
SELECT id, password_hash, deleted_at
FROM users
WHERE email = :email
LIMIT 1
""")


@auth_router.post("/login")
async def login(
    login_data: Login,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(GET_USER_QUERY, {"email": login_data.email})

    user = result.mappings().first()

    if not user or not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    if user["deleted_at"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is deleted"
        )

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
    result = await read_user(current_user_id, db)
    return result["user"]
