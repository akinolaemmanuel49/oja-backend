"""
Permission assignment service layer (grant/revoke).
Handles permission operations for users, groups, and roles with:
- Single and bulk operations
- Protection of root/admin accounts
- Consistent conflict handling (ON CONFLICT DO NOTHING)
"""

from typing import List

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def grant_single_permission(
    db: AsyncSession,
    target_type: str,  # "user", "group", "role"
    target_id: str,
    permission_code: str,
) -> (
    bool
):  # Possibly return error messages here; This might lead to better error messages
    """
    Grant a single permission to a user, group, or role.

    Args:
        db: Database session
        target_type: Entity type receiving the permission
        target_id: UUID of the target entity
        permission_code: Permission code to assign (must exist in permissions table)

    Returns:
        True if permission was newly granted, False if already existed or invalid target

    Raises:
        ValueError: If permission does not exist or invalid target
        RuntimeError: On unexpected database errors
    """
    try:
        # Find permission ID
        perm_result = await db.execute(
            text("SELECT id FROM permissions WHERE code = :code"),
            {"code": permission_code},
        )
        perm_id = perm_result.scalar()
        if not perm_id:
            return False

        # Prevent modifying permissions for root users
        if target_type == "user":
            query = text("SELECT id, is_root FROM users WHERE id=:target_id")
            result = await db.execute(query, {"target_id": target_id})
            user = result.first()
            if user and user.is_root:
                return False

        table_map = {
            "user": ("user_permissions", "user_id"),
            "group": ("group_permissions", "group_id"),
            "role": ("role_permissions", "role_id"),
        }
        if target_type not in table_map:
            return False

        table, id_col = table_map[target_type]

        await db.execute(
            text(f"""
            INSERT INTO {table} ({id_col}, permission_id, created_at)
            VALUES (:target_id, :perm_id, NOW())
            ON CONFLICT DO NOTHING
        """),
            {"target_id": target_id, "perm_id": perm_id},
        )

        await db.commit()
        return True
    except IntegrityError as e:
        if "user_permissions_user_id_fkey" in str(e):
            raise ValueError("User or permission does not exist")
        raise ValueError("Database constraint violation") from e
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to grant permission: {e}")


async def grant_multiple_permissions(
    db: AsyncSession, target_type: str, target_id: str, permission_codes: List[str]
) -> int:
    """
    Bulk grant multiple permissions to a user, group, or role.

    Args:
        db: Database session
        target_type: Entity type ("user", "group", "role")
        target_id: UUID of the target entity
        permission_codes: List of permission codes to grant

    Returns:
        Number of permissions successfully granted (newly added)

    Raises:
        ValueError: On constraint violations
        RuntimeError: On unexpected failures
    """
    try:
        table_map = {
            "user": ("user_permissions", "user_id"),
            "group": ("group_permissions", "group_id"),
            "role": ("role_permissions", "role_id"),
        }

        # Prevent modifying permissions for root users
        if target_type == "user":
            query = text("SELECT id, is_root FROM users WHERE id=:target_id")
            result = await db.execute(query, {"target_id": target_id})
            user = result.first()
            if user and user.is_root:
                return False

        if target_type not in table_map:
            return 0

        table_name, id_column = table_map[target_type]

        # Fetch valid permission IDs in bulk
        result = await db.execute(
            text("SELECT id, code FROM permissions WHERE code = ANY(:codes)"),
            {"codes": permission_codes},
        )
        valid_permissions = {row["code"]: row["id"] for row in result.mappings()}

        if not valid_permissions:
            return 0

        granted = 0

        for code in permission_codes:
            perm_id = valid_permissions.get(code)
            if not perm_id:
                continue

            await db.execute(
                text(f"""
                INSERT INTO {table_name} ({id_column}, permission_id, created_at)
                VALUES (:target_id, :perm_id, NOW())
                ON CONFLICT DO NOTHING
            """),
                {"target_id": target_id, "perm_id": perm_id},
            )
            granted += 1

        await db.commit()

        return granted
    except IntegrityError as e:
        if "user_permissions_user_id_fkey" in str(e):
            raise ValueError("User or permission does not exist")
        raise ValueError("Database constraint violation") from e
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to grant permissions: {e}")


async def revoke_single_permission(
    db: AsyncSession,
    target_type: str,  # "user", "group", "role"
    target_id: str,
    permission_code: str,
) -> bool:
    """
    Revoke a single permission from a user, group, or role.

    Args:
        db: Database session
        target_type: Entity type to revoke from
        target_id: UUID of the target entity
        permission_code: Permission code to remove

    Returns:
        True if permission was revoked, False if not found or invalid target
    """
    try:
        # Find permission ID
        perm_result = await db.execute(
            text("SELECT id FROM permissions WHERE code = :code"),
            {"code": permission_code},
        )
        perm_id = perm_result.scalar()
        if not perm_id:
            return False

        # Prevent modifying permissions for root users
        if target_type == "user":
            query = text("SELECT id, is_root FROM users WHERE id=:target_id")
            result = await db.execute(query, {"target_id": target_id})
            user = result.first()
            if user and user.is_root:
                return False

        table_map = {
            "user": ("user_permissions", "user_id"),
            "group": ("group_permissions", "group_id"),
            "role": ("role_permissions", "role_id"),
        }
        if target_type not in table_map:
            return False

        table, id_col = table_map[target_type]

        await db.execute(
            text(f"""
            DELETE FROM {table} WHERE {id_col} = :target_id AND permission_id = :perm_id
        """),
            {"target_id": target_id, "perm_id": perm_id},
        )

        await db.commit()
        return True
    except IntegrityError as e:
        if "user_permissions_user_id_fkey" in str(e):
            raise ValueError("User or permission does not exist")
        raise ValueError("Database constraint violation") from e
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to revoke permission: {e}")


async def revoke_multiple_permissions(
    db: AsyncSession, target_type: str, target_id: str, permission_codes: List[str]
) -> int:
    """
    Bulk revoke multiple permissions from a user, group, or role.

    Args:
        db: Database session
        target_type: Entity type ("user", "group", "role")
        target_id: UUID of the target entity
        permission_codes: List of permission codes to revoke

    Returns:
        Number of permissions successfully revoked
    """
    try:
        table_map = {
            "user": ("user_permissions", "user_id"),
            "group": ("group_permissions", "group_id"),
            "role": ("role_permissions", "role_id"),
        }

        # Prevent modifying permissions for root users
        if target_type == "user":
            query = text("SELECT id, is_root FROM users WHERE id=:target_id")
            result = await db.execute(query, {"target_id": target_id})
            user = result.first()
            if user and user.is_root:
                return False

        if target_type not in table_map:
            return 0

        table_name, id_column = table_map[target_type]

        # Fetch valid permission IDs in bulk
        result = await db.execute(
            text("SELECT id, code FROM permissions WHERE code = ANY(:codes)"),
            {"codes": permission_codes},
        )
        valid_permissions = {row["code"]: row["id"] for row in result.mappings()}

        if not valid_permissions:
            return 0

        granted = 0

        for code in permission_codes:
            perm_id = valid_permissions.get(code)
            if not perm_id:
                continue

            await db.execute(
                text(f"""
                DELETE FROM {table_name} WHERE {id_column} = :target_id AND permission_id = :perm_id
            """),
                {"target_id": target_id, "perm_id": perm_id},
            )
            granted += 1

        await db.commit()

        return granted
    except IntegrityError as e:
        if "user_permissions_user_id_fkey" in str(e):
            raise ValueError("User or permission does not exist")
        raise ValueError("Database constraint violation") from e
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to revoke permission: {e}")
