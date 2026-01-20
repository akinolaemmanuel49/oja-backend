from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio.session import AsyncSession

from src.core.security import verify_password

GET_USER_FOR_LOGIN_QUERY = text("""
SELECT id, password_hash, deleted_at
FROM users
WHERE email = :email
LIMIT 1
""")


async def login_service(db: AsyncSession, email: str, password: str) -> RowMapping:
    result = await db.execute(GET_USER_FOR_LOGIN_QUERY, {"email": email})

    user = result.mappings().first()

    if not user or not verify_password(password, user["password_hash"]):
        raise ValueError("Invalid credentials")

    if user["deleted_at"]:
        raise ValueError("User is deleted")

    return user
