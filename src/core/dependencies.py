from collections.abc import AsyncGenerator
from typing import Any, Dict

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.session import get_current_session
from src.database.session import AsyncSessionLocal

HAS_PERMISSIONS_QUERY = text("""
    SELECT 1
    FROM permissions p
    WHERE p.code = :permission_code
      AND (
          EXISTS (
              SELECT 1 FROM user_permissions up
              WHERE up.user_id = :user_id AND up.permission_id = p.id
          )
          OR EXISTS (
              SELECT 1 FROM user_groups ug
              JOIN group_permissions gp ON gp.group_id = ug.group_id
              WHERE ug.user_id = :user_id AND gp.permission_id = p.id
          )
          OR EXISTS (
              SELECT 1 FROM roles r
              JOIN role_permissions rp ON rp.role_id = r.id
              WHERE r.name = 'system' AND rp.permission_id = p.id  -- example: system roles
          )
      )
    LIMIT 1
""")


def get_app_settings() -> Settings:
    return get_settings()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to provide a database session per request"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()  # Commit if no exception
        except Exception:
            await session.rollback()  # Rollback on exception
            raise
        finally:
            await session.close()


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    session = await get_current_session(db, request)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return session


async def has_permission(db: AsyncSession, user_id: str, permission_code: str) -> bool:
    """
    Check if user has the required permission (direct, via group, or wildcard).
    """
    query = text("""
        SELECT DISTINCT p.code
        FROM permissions p
        WHERE (
            EXISTS (SELECT 1 FROM user_permissions up WHERE up.user_id = :user_id AND up.permission_id = p.id)
            OR EXISTS (SELECT 1 FROM user_groups ug
                       JOIN group_permissions gp ON gp.group_id = ug.group_id
                       WHERE ug.user_id = :user_id AND gp.permission_id = p.id)
        )
    """)
    result = await db.execute(query, {"user_id": user_id})
    user_codes = [row[0] for row in result.fetchall()]

    # Wildcard resolution
    for code in user_codes:
        if code == permission_code:  # exact match
            return True
        if code == "*":  # superuser wildcard
            return True
        if code.endswith("*") and permission_code.startswith(
            code[:-1]
        ):  # prefix wildcard
            return True

    return False


def require_permission(permission_code: str):
    """FastAPI dependency that enforces a specific permission."""

    async def dependency(
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        if not await has_permission(db, current_user["user_id"], permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission_code}",
            )
        return current_user

    return dependency
