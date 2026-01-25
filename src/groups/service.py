"""
Service layer for group management operations.

This module handles all business logic for groups including:
- Creating/updating/deleting groups
- Managing group membership (adding/removing users)
- Managing group permissions (granting/revoking)
- Listing groups and their members
"""

from typing import Any, Dict, List

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.responses import PaginatedResponse
from src.groups.schemas import (
    GroupCreate,
    GroupDetailOut,
    GroupMemberOut,
    GroupOut,
    GroupPermissionOut,
    GroupUpdate,
)

# =============================================================================
# SQL Queries
# =============================================================================

CREATE_GROUP_QUERY = text("""
    INSERT INTO groups (tenant_id, name, description, created_at, updated_at)
    VALUES (:tenant_id, :name, :description, NOW(), NOW())
    RETURNING id, tenant_id, name, description, created_at, updated_at
""")

GET_GROUP_BY_ID_QUERY = text("""
    SELECT id, tenant_id, name, description, created_at, updated_at
    FROM groups
    WHERE id = :group_id AND tenant_id = :tenant_id
""")

LIST_GROUPS_QUERY = text("""
    SELECT id, tenant_id, name, description, created_at, updated_at
    FROM groups
    WHERE tenant_id = :tenant_id
    ORDER BY name ASC
    LIMIT :limit OFFSET :offset
""")

COUNT_GROUPS_QUERY = text("""
    SELECT COUNT(*)
    FROM groups
    WHERE tenant_id = :tenant_id
""")

UPDATE_GROUP_QUERY = text("""
    UPDATE groups
    SET
        name = COALESCE(:name, name),
        description = COALESCE(:description, description),
        updated_at = NOW()
    WHERE id = :group_id AND tenant_id = :tenant_id
    RETURNING id, tenant_id, name, description, created_at, updated_at
""")

DELETE_GROUP_QUERY = text("""
    DELETE FROM groups
    WHERE id = :group_id AND tenant_id = :tenant_id
    RETURNING id
""")

GET_GROUP_DETAIL_QUERY = text("""
    SELECT
        g.id,
        g.tenant_id,
        g.name,
        g.description,
        g.created_at,
        g.updated_at,
        COUNT(DISTINCT ug.user_id) as member_count,
        COUNT(DISTINCT gp.permission_id) as permission_count
    FROM groups g
    LEFT JOIN user_groups ug ON g.id = ug.group_id
    LEFT JOIN group_permissions gp ON g.id = gp.group_id
    WHERE g.id = :group_id AND g.tenant_id = :tenant_id
    GROUP BY g.id, g.tenant_id, g.name, g.description, g.created_at, g.updated_at
""")

# Member management queries
ADD_USERS_TO_GROUP_QUERY = text("""
    INSERT INTO user_groups (user_id, group_id, created_at)
    SELECT u_id, :group_id, NOW()
    FROM UNNEST(:user_ids) AS u_id
    ON CONFLICT (user_id, group_id) DO NOTHING
    RETURNING user_id
""").bindparams(
    # This is the crucial change: wrapping the UUID in ARRAY
    bindparam("user_ids", type_=ARRAY(UUID(as_uuid=True))),
    bindparam("group_id", type_=UUID(as_uuid=True)),
)

REMOVE_USERS_FROM_GROUP_QUERY = text("""
    DELETE FROM user_groups
    WHERE group_id = :group_id
    AND user_id = ANY(:user_ids)
    RETURNING user_id
""")

LIST_GROUP_MEMBERS_QUERY = text("""
    SELECT
        u.id,
        u.email,
        u.first_name,
        u.last_name,
        u.full_name,
        u.is_active,
        ug.created_at as added_at
    FROM users u
    INNER JOIN user_groups ug ON u.id = ug.user_id
    WHERE ug.group_id = :group_id
    ORDER BY u.first_name, u.last_name
    LIMIT :limit OFFSET :offset
""")

COUNT_GROUP_MEMBERS_QUERY = text("""
    SELECT COUNT(*)
    FROM user_groups
    WHERE group_id = :group_id
""")

# Permission management queries
GRANT_PERMISSIONS_TO_GROUP_QUERY = text("""
    INSERT INTO group_permissions (group_id, permission_id, created_at)
    SELECT :group_id, p.id, NOW()
    FROM permissions p
    WHERE p.code = ANY(:permission_codes)
    ON CONFLICT (group_id, permission_id) DO NOTHING
    RETURNING permission_id
""")

REVOKE_PERMISSIONS_FROM_GROUP_QUERY = text("""
    DELETE FROM group_permissions
    WHERE group_id = :group_id
    AND permission_id IN (
        SELECT id FROM permissions WHERE code = ANY(:permission_codes)
    )
    RETURNING permission_id
""")

LIST_GROUP_PERMISSIONS_QUERY = text("""
    SELECT
        p.id,
        p.code,
        p.name,
        p.resource,
        p.action,
        p.description,
        gp.created_at as granted_at
    FROM permissions p
    INNER JOIN group_permissions gp ON p.id = gp.permission_id
    WHERE gp.group_id = :group_id
    ORDER BY p.resource, p.action
    LIMIT :limit OFFSET :offset
""")

COUNT_GROUP_PERMISSIONS_QUERY = text("""
    SELECT COUNT(*)
    FROM group_permissions
    WHERE group_id = :group_id
""")

# Verify user belongs to tenant (for security)
VERIFY_USER_IN_TENANT_QUERY = text("""
    SELECT id FROM users
    WHERE id = :user_id AND tenant_id = :tenant_id
""")


# =============================================================================
# Service Functions
# =============================================================================


async def create_group_service(
    db: AsyncSession,
    group_in: GroupCreate,
    tenant_id: str,
) -> GroupOut:
    """
    Create a new group in the tenant.

    Group names must be unique within a tenant.

    Args:
        db: Database session
        group_in: Group creation data
        tenant_id: Tenant ID (from current user)

    Returns:
        Created group

    Raises:
        ValueError: If group name already exists in tenant
    """
    try:
        result = await db.execute(
            CREATE_GROUP_QUERY,
            {
                "tenant_id": tenant_id,
                "name": group_in.name,
                "description": group_in.description,
            },
        )
        row = result.mappings().first()

        if not row:
            raise RuntimeError("Failed to create group")

        await db.commit()
        return GroupOut(**row)

    except IntegrityError as e:
        await db.rollback()
        if "groups_tenant_id_name_key" in str(e):
            raise ValueError(f"Group '{group_in.name}' already exists in this tenant")
        raise ValueError("Database constraint violation") from e
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Group creation failed: {str(e)}") from e


async def get_group_by_id_service(
    db: AsyncSession,
    group_id: str,
    tenant_id: str,
) -> GroupDetailOut:
    """
    Get a group by ID with member and permission counts.

    Args:
        db: Database session
        group_id: Group UUID
        tenant_id: Tenant ID (for isolation)

    Returns:
        Group details with counts

    Raises:
        ValueError: If group not found
    """
    result = await db.execute(
        GET_GROUP_DETAIL_QUERY,
        {
            "group_id": group_id,
            "tenant_id": tenant_id,
        },
    )
    row = result.mappings().first()

    if not row:
        raise ValueError(f"Group not found: {group_id}")

    return GroupDetailOut(**row)


async def list_groups_service(
    db: AsyncSession,
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse[GroupOut]:
    """
    List all groups in the tenant with pagination.

    Args:
        db: Database session
        tenant_id: Tenant ID
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Paginated list of groups
    """
    offset = (page - 1) * page_size

    # Get groups
    groups_result = await db.execute(
        LIST_GROUPS_QUERY,
        {
            "tenant_id": tenant_id,
            "limit": page_size,
            "offset": offset,
        },
    )
    groups_rows = groups_result.mappings().all()
    groups = [GroupOut(**row) for row in groups_rows]

    # Get total count
    count_result = await db.execute(
        COUNT_GROUPS_QUERY,
        {"tenant_id": tenant_id},
    )
    total = count_result.scalar_one()

    return PaginatedResponse[GroupOut](
        data=groups,
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_group_service(
    db: AsyncSession,
    group_id: str,
    group_update: GroupUpdate,
    tenant_id: str,
) -> GroupOut:
    """
    Update a group's details.

    Args:
        db: Database session
        group_id: Group UUID
        group_update: Update data
        tenant_id: Tenant ID (for isolation)

    Returns:
        Updated group

    Raises:
        ValueError: If group not found or name conflict
    """
    try:
        result = await db.execute(
            UPDATE_GROUP_QUERY,
            {
                "group_id": group_id,
                "tenant_id": tenant_id,
                "name": group_update.name,
                "description": group_update.description,
            },
        )
        row = result.mappings().first()

        if not row:
            raise ValueError(f"Group not found: {group_id}")

        await db.commit()
        return GroupOut(**row)

    except IntegrityError as e:
        await db.rollback()
        if "groups_tenant_id_name_key" in str(e):
            raise ValueError(f"Group name '{group_update.name}' already exists")
        raise ValueError("Database constraint violation") from e
    except ValueError:
        raise
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Group update failed: {str(e)}") from e


async def delete_group_service(
    db: AsyncSession,
    group_id: str,
    tenant_id: str,
) -> bool:
    """
    Delete a group.

    This will cascade delete:
    - All group memberships (user_groups)
    - All group permissions (group_permissions)

    Args:
        db: Database session
        group_id: Group UUID
        tenant_id: Tenant ID (for isolation)

    Returns:
        True if deleted, False if not found
    """
    try:
        result = await db.execute(
            DELETE_GROUP_QUERY,
            {
                "group_id": group_id,
                "tenant_id": tenant_id,
            },
        )
        row = result.mappings().first()
        await db.commit()

        return row is not None

    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Group deletion failed: {str(e)}") from e


# =============================================================================
# Member Management
# =============================================================================


async def add_users_to_group_service(
    db: AsyncSession,
    group_id: str,
    user_ids: List[str],
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Add users to a group.

    Both the user and group must belong to the same tenant.

    Args:
        db: Database session
        group_id: Group UUID
        user_ids: User UUIDs
        tenant_id: Tenant ID (for isolation)

    Returns:
        Dict with added, skipped, invalid users

    Raises:
        ValueError: If user or group not found in tenant
    """
    if not user_ids:
        return {"added": [], "skipped": [], "invalid": []}

    try:
        # Verify group belongs to tenant
        group_result = await db.execute(
            GET_GROUP_BY_ID_QUERY,
            {"group_id": group_id, "tenant_id": tenant_id},
        )
        if not group_result.first():
            raise ValueError(f"Group {group_id} not found")

        # Validate users belong to tenant
        valid_users_result = await db.execute(
            text("""
                SELECT id FROM users
                WHERE id = ANY(:user_ids) AND tenant_id = :tenant_id
            """),
            {"user_ids": user_ids, "tenant_id": tenant_id},
        )

        valid_user_ids = {row[0] for row in valid_users_result.fetchall()}
        invalid_user_ids = list(set(user_ids) - valid_user_ids)

        if not valid_user_ids:
            return {"added": [], "skipped": [], "invalid": invalid_user_ids}

        # Insert valid users
        insert_result = await db.execute(
            ADD_USERS_TO_GROUP_QUERY,
            {"group_id": group_id, "user_ids": list(valid_user_ids)},
        )

        added_ids = [row[0] for row in insert_result.fetchall()]
        skipped_ids = list(valid_user_ids - set(added_ids))

        await db.commit()

        return {
            "added": added_ids,
            "skipped": skipped_ids,
            "invalid": invalid_user_ids,
        }

    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to add users to group: {str(e)}") from e


async def remove_users_from_group_service(
    db: AsyncSession,
    group_id: str,
    user_ids: List[str],
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Remove users from a group.

    Args:
        db: Database session
        group_id: Group UUID
        user_ids: User UUIDs
        tenant_id: Tenant ID (for isolation)

    Returns:
        Dict with removed + not_found
    """
    if not user_ids:
        return {"removed": [], "not_found": []}

    try:
        # Verify group belongs to tenant
        group_result = await db.execute(
            GET_GROUP_BY_ID_QUERY,
            {"group_id": group_id, "tenant_id": tenant_id},
        )
        if not group_result.first():
            raise ValueError(f"Group {group_id} not found")

        delete_result = await db.execute(
            REMOVE_USERS_FROM_GROUP_QUERY,
            {"group_id": group_id, "user_ids": user_ids},
        )

        removed_ids = [row[0] for row in delete_result.fetchall()]
        not_found_ids = list(set(user_ids) - set(removed_ids))

        await db.commit()

        return {
            "removed": removed_ids,
            "not_found": not_found_ids,
        }

    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to remove users from group: {str(e)}") from e


async def list_group_members_service(
    db: AsyncSession,
    group_id: str,
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse[GroupMemberOut]:
    """
    List all members of a group with pagination.

    Args:
        db: Database session
        group_id: Group UUID
        tenant_id: Tenant ID (for isolation)
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Paginated list of group members

    Raises:
        ValueError: If group not found
    """
    # Verify group exists in tenant
    group_result = await db.execute(
        GET_GROUP_BY_ID_QUERY,
        {"group_id": group_id, "tenant_id": tenant_id},
    )
    if not group_result.first():
        raise ValueError(f"Group {group_id} not found")

    offset = (page - 1) * page_size

    # Get members
    members_result = await db.execute(
        LIST_GROUP_MEMBERS_QUERY,
        {
            "group_id": group_id,
            "limit": page_size,
            "offset": offset,
        },
    )
    members_rows = members_result.mappings().all()
    members = [GroupMemberOut(**row) for row in members_rows]

    # Get total count
    count_result = await db.execute(
        COUNT_GROUP_MEMBERS_QUERY,
        {"group_id": group_id},
    )
    total = count_result.scalar_one()

    return PaginatedResponse[GroupMemberOut](
        data=members,
        total=total,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# Permission Management
# =============================================================================


async def grant_permissions_to_group_service(
    db: AsyncSession,
    group_id: str,
    permission_codes: List[str],
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Grant permissions to a group.

    All members of the group will inherit these permissions.

    Args:
        db: Database session
        group_id: Group UUID
        permission_codes: Permission codes (e.g., ["users:read", "users:write"])
        tenant_id: Tenant ID (for isolation)

    Returns:
        A dictionary with the following keys:
            - "granted_count": The number of permissions granted
            - "requested_count": The total number of permissions requested
            - "already_had": The number of permissions already had

    Raises:
        ValueError: If group or permission not found
    """
    try:
        # Verify group exists
        group_result = await db.execute(
            GET_GROUP_BY_ID_QUERY,
            {"group_id": group_id, "tenant_id": tenant_id},
        )
        if not group_result.first():
            raise ValueError(f"Group {group_id} not found")

        # Validate permissions exist
        perm_check = await db.execute(
            text("SELECT code FROM permissions WHERE code = ANY(:codes)"),
            {"codes": permission_codes},
        )
        found_codes = {row.code for row in perm_check.mappings()}
        missing = set(permission_codes) - found_codes

        if missing:
            raise ValueError(f"Permissions not found: {sorted(missing)}")

        # Insert permissions
        result = await db.execute(
            GRANT_PERMISSIONS_TO_GROUP_QUERY,
            {
                "group_id": group_id,
                "permission_codes": permission_codes,
            },
        )
        inserted = [row.permission_id for row in result.mappings()]

        await db.commit()

        return {
            "granted_count": len(inserted),
            "requested_count": len(permission_codes),
            "already_had": len(permission_codes) - len(inserted),
        }

    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Bulk grant failed: {str(e)}") from e


async def revoke_permissions_from_group_service(
    db: AsyncSession,
    group_id: str,
    permission_codes: List[str],
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Revoke permissions from a group.

    Members will lose these permissions unless they have it assigned directly.

    Args:
        db: Database session
        group_id: Group UUID
        permission_codes: Permission codes (e.g., ["users:read", "users:write"])
        tenant_id: Tenant ID (for isolation)

    Returns:
        A dictionary with the following keys:
            - "revoked_count": The number of permissions revoked
            - "requested_count": The total number of permissions requested
            - "not_present": The number of permissions not present

    Raises:
        ValueError: If group not found
    """
    try:
        # Verify group exists
        group_result = await db.execute(
            GET_GROUP_BY_ID_QUERY,
            {"group_id": group_id, "tenant_id": tenant_id},
        )
        if not group_result.first():
            raise ValueError(f"Group {group_id} not found")

        # Delete permissions
        result = await db.execute(
            REVOKE_PERMISSIONS_FROM_GROUP_QUERY,
            {
                "group_id": group_id,
                "permission_codes": permission_codes,
            },
        )
        deleted = [row.permission_id for row in result.mappings()]

        await db.commit()

        return {
            "revoked_count": len(deleted),
            "requested_count": len(permission_codes),
            "not_present": len(permission_codes) - len(deleted),
        }

    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Bulk revoke failed: {str(e)}") from e


async def list_group_permissions_service(
    db: AsyncSession,
    group_id: str,
    tenant_id: str,
    page: int = 1,
    page_size: int = 50,
) -> PaginatedResponse[GroupPermissionOut]:
    """
    List all permissions assigned to a group.

    Args:
        db: Database session
        group_id: Group UUID
        tenant_id: Tenant ID (for isolation)
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Paginated list of group permissions

    Raises:
        ValueError: If group not found
    """
    # Verify group exists in tenant
    group_result = await db.execute(
        GET_GROUP_BY_ID_QUERY,
        {"group_id": group_id, "tenant_id": tenant_id},
    )
    if not group_result.first():
        raise ValueError(f"Group {group_id} not found")

    offset = (page - 1) * page_size

    # Get permissions
    perms_result = await db.execute(
        LIST_GROUP_PERMISSIONS_QUERY,
        {
            "group_id": group_id,
            "limit": page_size,
            "offset": offset,
        },
    )
    perms_rows = perms_result.mappings().all()
    permissions = [GroupPermissionOut(**row) for row in perms_rows]

    # Get total count
    count_result = await db.execute(
        COUNT_GROUP_PERMISSIONS_QUERY,
        {"group_id": group_id},
    )
    total = count_result.scalar_one()

    return PaginatedResponse[GroupPermissionOut](
        data=permissions,
        total=total,
        page=page,
        page_size=page_size,
    )
