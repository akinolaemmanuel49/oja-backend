from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings

SESSION_COOKIE = "session_id"
SESSION_LIFETIME = timedelta(days=settings.APP_SESSION_LIFETIME)

INSERT_SESSION_QUERY = text("""
INSERT INTO sessions (user_id, token, ip_address, user_agent, expires_at, created_at, updated_at)
VALUES (:user_id, :token, :ip, :ua, :expires_at, NOW(), NOW())
""")

GET_SESSION_QUERY = text("""
SELECT user_id, expires_at
FROM sessions
WHERE token = :token AND expires_at > NOW()
LIMIT 1
""")

DELETE_SESSION_QUERY = text("DELETE FROM sessions WHERE token = :token")


async def create_session(
    db: AsyncSession, user_id: str, request: Request, response: Response
) -> None:
    """Create a new session and set cookie."""
    token = str(uuid4())
    expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME

    await db.execute(
        INSERT_SESSION_QUERY,
        {
            "user_id": user_id,
            "token": token,
            "ip": request.client.host if request.client is not None else None,
            "ua": request.headers.get("user-agent"),
            "expires_at": expires_at,
        },
    )

    await db.commit()

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
    )


async def get_current_session(db: AsyncSession, request: Request) -> Optional[dict]:
    """Validate session from cookie and return user_id if valid."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    result = await db.execute(
        GET_SESSION_QUERY,
        {"token": token},
    )

    row = result.mappings().first()
    if not row:
        return None

    if row["expires_at"] < datetime.now(timezone.utc):
        await db.execute(DELETE_SESSION_QUERY, {"token": token})
        await db.commit()
        return None

    return {"user_id": str(row["user_id"])}


async def destroy_session(
    db: AsyncSession, request: Request, response: Response
) -> None:
    """Logout – delete session and clear cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await db.execute(DELETE_SESSION_QUERY, {"token": token})
        await db.commit()

    response.delete_cookie(SESSION_COOKIE)
