from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_user_permissions(db: AsyncSession, user_id: str) -> List[str]:
    """
    Return all effective permission codes for a user (direct + via groups).
    Wildcards are resolved to concrete codes (never return '*').
    """
    query = text("""
        SELECT DISTINCT p.code
        FROM permissions p
        WHERE (
            EXISTS (SELECT 1 FROM user_permissions up
                    WHERE up.user_id = :user_id AND up.permission_id = p.id)
            OR EXISTS (SELECT 1 FROM user_groups ug
                       JOIN group_permissions gp ON gp.group_id = ug.group_id
                       WHERE ug.user_id = :user_id AND gp.permission_id = p.id)
        )
    """)
    result = await db.execute(query, {"user_id": user_id})
    codes = [row[0] for row in result.fetchall()]

    # Resolve wildcards to concrete permissions (application-side)
    resolved = set()
    for code in codes:
        if code == "*":
            # Return all known permissions (or fetch all from DB)
            all_result = await db.execute(text("SELECT code FROM permissions"))
            resolved.update(row[0] for row in all_result.fetchall())
        elif code.endswith("*"):
            base = code[:-1]
            wildcard_result = await db.execute(
                text("SELECT code FROM permissions WHERE code LIKE :base || '%'"),
                {"base": base},
            )
            resolved.update(row[0] for row in wildcard_result.fetchall())
        else:
            resolved.add(code)

    return sorted(resolved)


async def has_permission(db: AsyncSession, user_id: str, required_code: str) -> bool:
    """
    Check whether user has the required permission.
    Supports wildcard matching (application-side).
    """
    user_codes = await list_user_permissions(db, user_id)
    for code in user_codes:
        if code == required_code:
            return True
        if code.endswith("*") and required_code.startswith(code[:-1]):
            return True
    return False


async def grant_single_permission(
    db: AsyncSession,
    target_type: str,  # "user", "group", "role"
    target_id: str,
    permission_code: str,
) -> (
    bool
):  # Possibly return error messages here; This might lead to better error messages
    """
    Assign a permission to a user/group/role.
    Returns True if granted, False if already exists or invalid.
    """
    # Find permission ID
    perm_result = await db.execute(
        text("SELECT id FROM permissions WHERE code = :code"), {"code": permission_code}
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


async def grant_multiple_permissions(
    db: AsyncSession, target_type: str, target_id: str, permission_codes: List[str]
) -> int:
    """
    Bulk assign permissions to target.
    Returns number of successfully granted permissions.
    """
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


async def revoke_single_permission(
    db: AsyncSession,
    target_type: str,  # "user", "group", "role"
    target_id: str,
    permission_code: str,
) -> bool:
    """
    Revoke a permission from a user/group/role.
    Returns True if revoked, False if not found or invalid.
    """
    # Find permission ID
    perm_result = await db.execute(
        text("SELECT id FROM permissions WHERE code = :code"), {"code": permission_code}
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


async def revoke_multiple_permissions(
    db: AsyncSession, target_type: str, target_id: str, permission_codes: List[str]
) -> int:
    """
    Revoke permissions from target.
    Returns number of successfully revoked permissions.
    """
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
