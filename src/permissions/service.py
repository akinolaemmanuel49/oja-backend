"""
Permission resolution and authorization service layer.
This module handles:
- Listing effective permissions for a user (direct + group-inherited)
- Checking if a user has a specific permission (with wildcard support)
- Centralized tenancy validation across entity types
"""

from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_user_permissions(db: AsyncSession, user_id: str) -> List[str]:
    """
    Return all effective permission codes for a user (direct assignments + inherited via groups).
    Wildcards (*) are resolved to concrete permission codes — never returns wildcard strings.

    Args:
        db: Database session
        user_id: UUID of the user

    Returns:
        Sorted list of unique, concrete permission codes the user possesses

    Note:
        Wildcard resolution happens application-side for performance and flexibility.
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
    Check whether the user has the required permission (supports wildcard matching).

    Args:
        db: Database session
        user_id: UUID of the user to check
        required_code: Permission code to verify (e.g. "orders:read", "products:*")

    Returns:
        True if user has the permission (directly or via wildcard/group), False otherwise
    """
    user_codes = await list_user_permissions(db, user_id)
    for code in user_codes:
        if code == required_code:
            return True
        if code.endswith("*") and required_code.startswith(code[:-1]):
            return True
    return False


async def tenancy_check(
    db: AsyncSession, origin_id, origin_type, destination_id, destination_type
):
    """
    Verify that two entities belong to the same tenant (multi-tenancy isolation).

    Args:
        db: Database session
        origin_id: ID of the source entity
        origin_type: Type of source entity ("user", "group", "role")
        destination_id: ID of the target entity
        destination_type: Type of target entity ("user", "group", "role")

    Returns:
        True if both entities are in the same tenant

    Raises:
        ValueError: If invalid entity type is provided
    """
    match origin_type:
        case "user":
            origin_table = "users"
        case "group":
            origin_table = "groups"
        case "role":
            origin_table = "roles"
        case _:
            raise ValueError("Invalid origin type")

    match destination_type:
        case "user":
            destination_table = "users"
        case "group":
            destination_table = "groups"
        case "role":
            destination_table = "roles"
        case _:
            raise ValueError("Invalid destination type")

    origin_entity = await db.execute(
        text(f"SELECT tenant_id FROM {origin_table} WHERE id = :id"), {"id": origin_id}
    )
    destination_entity = await db.execute(
        text(f"SELECT tenant_id FROM {destination_table} WHERE id = :id"),
        {"id": destination_id},
    )

    origin_tenant_id = origin_entity.scalar_one()
    destination_tenant_id = destination_entity.scalar_one()

    return origin_tenant_id == destination_tenant_id
