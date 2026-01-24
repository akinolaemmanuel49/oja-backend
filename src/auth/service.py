"""
Authentication core service layer.
Handles credential verification during login.
"""

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
    """
    Authenticate user credentials and return minimal user data for session creation.

    Args:
        db: Database session
        email: User email
        password: Plaintext password

    Returns:
        RowMapping with user id and other minimal fields needed for token creation

    Raises:
        ValueError: On invalid credentials or deleted account
    """
    result = await db.execute(GET_USER_FOR_LOGIN_QUERY, {"email": email})

    user = result.mappings().first()

    if not user or not verify_password(password, user["password_hash"]):
        raise ValueError("Invalid credentials")

    if user["deleted_at"]:
        raise ValueError("User is deleted")

    return user
