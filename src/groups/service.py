"""
Service layer for group management operations.

This module handles all business logic for groups including:
- Creating/updating/deleting groups
- Managing group membership (adding/removing users)
- Managing group permissions (granting/revoking)
- Listing groups and their members
"""

from sqlalchemy import text
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
ADD_USER_TO_GROUP_QUERY = text("""
    INSERT INTO user_groups (user_id, group_id, created_at)
    VALUES (:user_id, :group_id, NOW())
    ON CONFLICT (user_id, group_id) DO NOTHING
    RETURNING user_id, group_id, created_at
""")

REMOVE_USER_FROM_GROUP_QUERY = text("""
    DELETE FROM user_groups
    WHERE user_id = :user_id AND group_id = :group_id
    RETURNING user_id, group_id
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
GRANT_PERMISSION_TO_GROUP_QUERY = text("""
    INSERT INTO group_permissions (group_id, permission_id, created_at)
    SELECT :group_id, p.id, NOW()
    FROM permissions p
    WHERE p.code = :permission_code
    ON CONFLICT (group_id, permission_id) DO NOTHING
    RETURNING group_id, permission_id, created_at
""")

REVOKE_PERMISSION_FROM_GROUP_QUERY = text("""
    DELETE FROM group_permissions
    WHERE group_id = :group_id
    AND permission_id = (SELECT id FROM permissions WHERE code = :permission_code)
    RETURNING group_id, permission_id
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


async def add_user_to_group_service(
    db: AsyncSession,
    group_id: str,
    user_id: str,
    tenant_id: str,
) -> bool:
    """
    Add a user to a group.

    Both the user and group must belong to the same tenant.

    Args:
        db: Database session
        group_id: Group UUID
        user_id: User UUID
        tenant_id: Tenant ID (for isolation)

    Returns:
        True if user was added, False if already in group

    Raises:
        ValueError: If user or group not found in tenant
    """
    try:
        # Verify user belongs to tenant
        user_result = await db.execute(
            VERIFY_USER_IN_TENANT_QUERY,
            {"user_id": user_id, "tenant_id": tenant_id},
        )
        if not user_result.scalar():
            raise ValueError(f"User {user_id} not found in tenant")

        # Verify group belongs to tenant
        group_result = await db.execute(
            GET_GROUP_BY_ID_QUERY,
            {"group_id": group_id, "tenant_id": tenant_id},
        )
        if not group_result.first():
            raise ValueError(f"Group {group_id} not found")

        # Add user to group
        result = await db.execute(
            ADD_USER_TO_GROUP_QUERY,
            {"user_id": user_id, "group_id": group_id},
        )
        row = result.mappings().first()
        await db.commit()

        # Return True if inserted, False if already existed (ON CONFLICT DO NOTHING)
        return row is not None

    except ValueError:
        raise
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to add user to group: {str(e)}") from e


async def remove_user_from_group_service(
    db: AsyncSession,
    group_id: str,
    user_id: str,
    tenant_id: str,
) -> bool:
    """
    Remove a user from a group.

    Args:
        db: Database session
        group_id: Group UUID
        user_id: User UUID
        tenant_id: Tenant ID (for isolation)

    Returns:
        True if user was removed, False if not in group
    """
    try:
        # Verify group belongs to tenant (security check)
        group_result = await db.execute(
            GET_GROUP_BY_ID_QUERY,
            {"group_id": group_id, "tenant_id": tenant_id},
        )
        if not group_result.first():
            raise ValueError(f"Group {group_id} not found")

        # Remove user from group
        result = await db.execute(
            REMOVE_USER_FROM_GROUP_QUERY,
            {"user_id": user_id, "group_id": group_id},
        )
        row = result.mappings().first()
        await db.commit()

        return row is not None

    except ValueError:
        raise
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to remove user from group: {str(e)}") from e


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


async def grant_permission_to_group_service(
    db: AsyncSession,
    group_id: str,
    permission_code: str,
    tenant_id: str,
) -> bool:
    """
    Grant a permission to a group.

    All members of the group will inherit this permission.

    Args:
        db: Database session
        group_id: Group UUID
        permission_code: Permission code (e.g., "users:read")
        tenant_id: Tenant ID (for isolation)

    Returns:
        True if permission was granted, False if already had it

    Raises:
        ValueError: If group or permission not found
    """
    try:
        # Verify group exists in tenant
        group_result = await db.execute(
            GET_GROUP_BY_ID_QUERY,
            {"group_id": group_id, "tenant_id": tenant_id},
        )
        if not group_result.first():
            raise ValueError(f"Group {group_id} not found")

        # Grant permission
        result = await db.execute(
            GRANT_PERMISSION_TO_GROUP_QUERY,
            {"group_id": group_id, "permission_code": permission_code},
        )
        row = result.mappings().first()

        if row is None:
            # Check if permission exists
            perm_check = await db.execute(
                text("SELECT id FROM permissions WHERE code = :code"),
                {"code": permission_code},
            )
            if not perm_check.scalar():
                raise ValueError(f"Permission '{permission_code}' not found")

            # Permission already granted (ON CONFLICT DO NOTHING)
            return False

        await db.commit()
        return True

    except ValueError:
        raise
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to grant permission: {str(e)}") from e


async def revoke_permission_from_group_service(
    db: AsyncSession,
    group_id: str,
    permission_code: str,
    tenant_id: str,
) -> bool:
    """
    Revoke a permission from a group.

    Members will lose this permission unless they have it assigned directly.

    Args:
        db: Database session
        group_id: Group UUID
        permission_code: Permission code (e.g., "users:read")
        tenant_id: Tenant ID (for isolation)

    Returns:
        True if permission was revoked, False if didn't have it

    Raises:
        ValueError: If group not found
    """
    try:
        # Verify group exists in tenant
        group_result = await db.execute(
            GET_GROUP_BY_ID_QUERY,
            {"group_id": group_id, "tenant_id": tenant_id},
        )
        if not group_result.first():
            raise ValueError(f"Group {group_id} not found")

        # Revoke permission
        result = await db.execute(
            REVOKE_PERMISSION_FROM_GROUP_QUERY,
            {"group_id": group_id, "permission_code": permission_code},
        )
        row = result.mappings().first()
        await db.commit()

        return row is not None

    except ValueError:
        raise
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to revoke permission: {str(e)}") from e


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
