"""
User and tenant provisioning service layer.
Handles:
- User creation (with optional new tenant for root users)
- Tenant bootstrapping
- User listing with pagination
- Managing user permissions (granting/revoking)
- Managing user groups (adding/removing)
"""

from typing import Any, Dict, List, Literal, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.responses import PaginatedResponse
from src.core.security import hash_password
from src.core.utils import ALPHANUMERIC, ALPHANUMERIC_LOWER, generate_random_string
from src.groups.schemas import GroupOut
from src.groups.service import GET_GROUP_BY_ID_QUERY
from src.permissions.service import list_user_permissions
from src.users.schemas import UserCreate, UserOut, UserPermissionOut, UserUpdate

INSERT_TENANT_QUERY = text("""
    INSERT INTO tenants (alias, name, status, created_at, updated_at)
    VALUES (:alias, :name, 'active', NOW(), NOW())
    RETURNING id
""")

INSERT_USER_QUERY = text("""
    INSERT INTO users (
        email,
        password_hash,
        first_name,
        last_name,
        full_name,
        tenant_id,
        is_root,
        created_at,
        updated_at
    )
    VALUES (
        :email,
        :password_hash,
        :first_name,
        :last_name,
        :full_name,
        :tenant_id,
        :is_root,
        NOW(),
        NOW()
    )
    RETURNING
        id,
        email,
        first_name,
        last_name,
        full_name,
        is_active,
        is_root,
        tenant_id,
        created_at
""")

UPDATE_TENANT_QUERY = text("""
    UPDATE tenants
    SET owner_id = :owner_id, updated_at = NOW()
    WHERE id = :tenant_id
""")

READ_USER_QUERY_BY_ID = text("""
     SELECT id, email, first_name, last_name, full_name, tenant_id, is_active, is_root, created_at, updated_at
     FROM users
     WHERE id = :user_id
 """)


READ_USER_QUERY_BY_EMAIL = text("""
     SELECT id, email, first_name, last_name, full_name, tenant_id, is_active, is_root, created_at, updated_at
     FROM users
     WHERE email = :email
 """)

READ_USERS_QUERY_BY_TENANT_ID = text("""
    SELECT id, email, first_name, last_name, full_name, tenant_id,
           is_active, is_root, created_at, updated_at
    FROM users
    WHERE tenant_id = :tenant_id
    ORDER BY created_at DESC
    LIMIT :limit OFFSET :offset
""")

COUNT_USERS_QUERY_BY_TENANT_ID = text("""
    SELECT COUNT(*)
    FROM users
    WHERE tenant_id = :tenant_id
""")

UPDATE_USER_QUERY_TEMPLATE = """
    UPDATE users
    SET {updates_clause}, updated_at = NOW()
    WHERE id = :user_id AND tenant_id = :tenant_id
    RETURNING
        id,
        email,
        first_name,
        last_name,
        full_name,
        is_active,
        is_root,
        tenant_id,
        created_at,
        updated_at
"""

GET_USER_FOR_UPDATE_QUERY = text("""
    SELECT id, email, tenant_id
    FROM users
    WHERE id = :user_id AND tenant_id = :tenant_id
    FOR UPDATE
""")

SOFT_DELETE_USER_QUERY = text("""
    UPDATE users
    SET
        is_active = FALSE,
        updated_at = NOW(),
        deleted_at = NOW()
    WHERE id = :user_id
    AND tenant_id = :tenant_id
    RETURNING id
""")

# Permission management queries
GET_USER_BY_ID_QUERY = text("""
    SELECT id, email, first_name, last_name, full_name, tenant_id, is_active, is_root, created_at, updated_at
    FROM users
    WHERE id = :user_id AND tenant_id = :tenant_id
""")

LIST_USER_PERMISSIONS_QUERY = text("""
    SELECT
        p.id,
        p.code,
        p.name,
        p.resource,
        p.action,
        p.description,
        up.created_at as granted_at
    FROM permissions p
    INNER JOIN user_permissions up ON p.id = up.permission_id
    WHERE up.user_id = :user_id
    ORDER BY p.resource, p.action
    LIMIT :limit OFFSET :offset
""")

COUNT_USER_PERMISSIONS_QUERY = text("""
    SELECT COUNT(*)
    FROM user_permissions
    WHERE user_id = :user_id
""")

GRANT_PERMISSIONS_TO_USER_QUERY = text("""
    INSERT INTO user_permissions (user_id, permission_id, created_at)
    SELECT :user_id, p.id, NOW()
    FROM permissions p
    WHERE p.code = ANY(:permission_codes)
    ON CONFLICT (user_id, permission_id) DO NOTHING
    RETURNING permission_id
""")

REVOKE_PERMISSIONS_FROM_USER_QUERY = text("""
    DELETE FROM user_permissions
    WHERE user_id = :user_id
    AND permission_id IN (
        SELECT id FROM permissions WHERE code = ANY(:permission_codes)
    )
    RETURNING permission_id
""")

# Group management queries
ADD_USER_TO_GROUP_QUERY = text("""
    INSERT INTO user_groups (user_id, group_id, created_at)
    VALUES (:user_id, :group_id, NOW())
    ON CONFLICT (user_id, group_id) DO NOTHING
    RETURNING user_id
""")


REMOVE_USER_FROM_GROUP_QUERY = text("""
    DELETE FROM user_groups
    WHERE group_id = :group_id
    AND user_id = user_id
    RETURNING user_id
""")

LIST_GROUPS_QUERY = text("""
    SELECT
        id,
        tenant_id,
        name,
        description,
        created_at,
        updated_at
    FROM groups
    WHERE tenant_id = :tenant_id
    AND id IN (
        SELECT group_id FROM user_groups WHERE user_id = :user_id
    )
    ORDER BY name
    LIMIT :limit OFFSET :offset
""")

COUNT_USER_MEMBER_GROUPS_QUERY = text("""
    SELECT COUNT(*)
    FROM user_groups
    WHERE user_id = :user_id
""")


async def create_user_service(
    db: AsyncSession,
    user_in: UserCreate,
    is_root: bool = False,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new user, optionally creating a new tenant for root/super-admin users.

    Args:
        db: Database session
        user_in: User creation payload
        is_root: Whether this is a root/owner user (implies new tenant if tenant_id=None)
        tenant_id: Existing tenant to place user in (if not creating new tenant)

    Returns:
        Dictionary with "user" and optionally "tenant" keys

    Raises:
        ValueError: If email already registered
        RuntimeError: On creation failure
    """
    try:
        hashed_pw = hash_password(user_in.password)

        new_tenant_id: Optional[str] = None

        # Explicit initialization for static analysis
        alias: Optional[str] = None
        name: Optional[str] = None

        # Root user case: create tenant first
        if is_root and tenant_id is None:
            alias = generate_random_string(
                pattern="XXXX-XXXX-XXXX",
                chars=ALPHANUMERIC_LOWER,
            )
            name = generate_random_string(
                pattern="Tenant-XXXXXX",
                chars=ALPHANUMERIC,
            )

            tenant_result = await db.execute(
                INSERT_TENANT_QUERY,
                {"alias": alias, "name": name},
            )
            tenant_row = tenant_result.mappings().first()
            if not tenant_row:
                raise RuntimeError("Failed to create root tenant")

            new_tenant_id = str(tenant_row["id"])
            tenant_id = new_tenant_id

        # Create user
        user_result = await db.execute(
            INSERT_USER_QUERY,
            {
                "email": user_in.email,
                "password_hash": hashed_pw,
                "first_name": user_in.first_name,
                "last_name": user_in.last_name,
                "full_name": f"{user_in.first_name} {user_in.last_name}".strip(),
                "tenant_id": tenant_id,
                "is_root": is_root,
            },
        )

        user_row = user_result.mappings().first()
        if not user_row:
            raise RuntimeError("Failed to create user")

        new_user_id = user_row["id"]

        if is_root:
            # Assign existing wildcard permission
            await db.execute(
                text("""
                INSERT INTO user_permissions (user_id, permission_id, created_at)
                SELECT :user_id, p.id, NOW()
                FROM permissions p
                WHERE p.code = '*'
                ON CONFLICT DO NOTHING;
            """),
                {"user_id": new_user_id},
            )

        # If we created a tenant, set its owner
        if new_tenant_id is not None:
            await db.execute(
                UPDATE_TENANT_QUERY,
                {
                    "owner_id": new_user_id,
                    "tenant_id": new_tenant_id,
                },
            )

        await db.commit()  # Explicitly commit the transaction

        result: Dict[str, Any] = {
            "user": dict(user_row),
        }

        # Include tenant info only if a tenant was actually created
        if new_tenant_id is not None:
            result["tenant"] = {
                "id": tenant_id,
                "alias": alias,
                "name": name,
            }

        return result

    except IntegrityError as e:
        print(e)
        if "users_email_key" in str(e):
            raise ValueError("Email already registered")
        raise ValueError("Database constraint violation") from e
    except Exception as e:
        print(e)
        await db.rollback()
        raise RuntimeError(f"User creation failed: {str(e)}") from e


async def get_user_by_id_service(user_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Retrieve user by ID including effective permissions.

    Args:
        user_id: User UUID
        db: Database session

    Returns:
        Dictionary with "user" and "permissions" keys

    Raises:
        ValueError: If user not found
    """
    user_result = await db.execute(READ_USER_QUERY_BY_ID, {"user_id": user_id})
    user_row = user_result.mappings().first()
    if not user_row:
        raise ValueError(f"User not found: {user_id}")

    permissions = await list_user_permissions(db, user_id)

    result: Dict[str, Any] = {
        "user": dict(user_row),
        "permissions": permissions,
    }

    return result


async def get_user_by_email_service(email: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Retrieve basic user information by email.

    Args:
        email: User's email address
        db: Database session

    Returns:
        Dictionary with user data

    Raises:
        ValueError: If user not found
    """
    user_result = await db.execute(READ_USER_QUERY_BY_EMAIL, {"email": email})
    user_row = user_result.mappings().first()
    if not user_row:
        raise ValueError(f"User not found: {email}")

    result: Dict[str, Any] = {
        "user": dict(user_row),
    }

    return result


async def get_users_service(
    tenant_id: str,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse:
    """
    Paginated list of users in a tenant.

    Args:
        tenant_id: Tenant identifier
        db: Database session
        page: Page number (1-based)
        page_size: Records per page

    Returns:
        PaginatedResponse containing UserOut objects
    """
    offset = (page - 1) * page_size

    # Fetch users
    users_result = await db.execute(
        READ_USERS_QUERY_BY_TENANT_ID,
        {
            "tenant_id": tenant_id,
            "limit": page_size,
            "offset": offset,
        },
    )

    user_rows = users_result.mappings().all()
    users = [UserOut(**row) for row in user_rows]

    # Fetch total count
    count_result = await db.execute(
        COUNT_USERS_QUERY_BY_TENANT_ID,
        {"tenant_id": tenant_id},
    )
    total = count_result.scalar_one()

    return PaginatedResponse[UserOut](
        data=users,
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_user_service(
    db: AsyncSession,
    user_id: str,
    tenant_id: str,
    update_data: UserUpdate,
) -> Dict[str, Any]:
    """
    Update a user's information.

    Args:
        db: Database session
        user_id: User ID to update
        tenant_id: Tenant ID for authorization
        update_data: Partial update fields

    Returns:
        Dictionary with updated user data

    Raises:
        ValueError: If user not found or email already exists
        RuntimeError: On update failure
    """
    # Validate that there's something to update
    if not any(
        [
            update_data.email is not None,
            update_data.first_name is not None,
            update_data.last_name is not None,
        ]
    ):
        raise ValueError("No update fields provided")

    try:
        # Check if user exists and lock row for update
        user_check = await db.execute(
            GET_USER_FOR_UPDATE_QUERY, {"user_id": user_id, "tenant_id": tenant_id}
        )
        existing_user = user_check.mappings().first()

        if not existing_user:
            raise ValueError(f"User not found: {user_id}")

        # Build dynamic update query
        updates = []
        params: Dict[str, Any] = {
            "user_id": user_id,
            "tenant_id": tenant_id,
        }

        # Email update
        if update_data.email is not None:
            if update_data.email != existing_user["email"]:
                updates.append("email = :email")
                params["email"] = update_data.email

        # Name updates
        if update_data.first_name is not None:
            updates.append("first_name = :first_name")
            params["first_name"] = update_data.first_name

        if update_data.last_name is not None:
            updates.append("last_name = :last_name")
            params["last_name"] = update_data.last_name

        # Update full_name if either first or last name changes
        if update_data.first_name is not None or update_data.last_name is not None:
            first_name = (
                update_data.first_name
                if update_data.first_name is not None
                else existing_user.get("first_name", "")
            )
            last_name = (
                update_data.last_name
                if update_data.last_name is not None
                else existing_user.get("last_name", "")
            )
            updates.append("full_name = :full_name")
            params["full_name"] = f"{first_name} {last_name}".strip()

        # If no actual updates after processing (e.g., same email provided)
        if not updates:
            # Return current user data without error
            result = await db.execute(
                text("""
                    SELECT id, email, first_name, last_name, full_name,
                           is_active, is_root, tenant_id, created_at, updated_at
                    FROM users
                    WHERE id = :user_id AND tenant_id = :tenant_id
                """),
                {"user_id": user_id, "tenant_id": tenant_id},
            )
            user_row = result.mappings().first()
            return {"user": dict(user_row)} if user_row else {}

        # Execute update
        updates_clause = ", ".join(updates)
        update_query = text(
            UPDATE_USER_QUERY_TEMPLATE.format(updates_clause=updates_clause)
        )

        result = await db.execute(update_query, params)
        user_row = result.mappings().first()

        if not user_row:
            raise RuntimeError("Failed to update user")

        await db.commit()

        return {"user": dict(user_row)}

    except IntegrityError as e:
        await db.rollback()
        if "users_email_key" in str(e):
            raise ValueError("Email already registered")
        raise ValueError("Database constraint violation") from e
    except ValueError:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to update user: {str(e)}") from e


async def delete_user_service(
    db: AsyncSession,
    user_id: str,
    tenant_id: str,
):
    """
    Delete a user by ID (soft delete)

    Args:
        db: Database session
        user_id: User ID to update
        tenant_id: Tenant ID for authorization

    Raises:
        ValueError: If user not found
        RuntimeError: On update failure
    """

    try:
        # Check if user exists and lock row for update
        user_check = await db.execute(
            GET_USER_FOR_UPDATE_QUERY, {"user_id": user_id, "tenant_id": tenant_id}
        )
        existing_user = user_check.mappings().first()

        if not existing_user:
            raise ValueError(f"User not found: {user_id}")

        # Soft delete user
        result = await db.execute(
            SOFT_DELETE_USER_QUERY,
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
            },
        )

        await db.commit()

        return result.scalar_one_or_none()

    except IntegrityError as e:
        await db.rollback()
        raise ValueError("Database constraint violation") from e
    except ValueError:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to delete user: {str(e)}") from e


async def list_user_permissions_service(
    db: AsyncSession,
    user_id: str,
    tenant_id: str,
    page: int = 1,
    page_size: int = 50,
) -> PaginatedResponse[UserPermissionOut]:
    """
    List all permissions assigned to a user.

    Args:
        db: Database session
        user_id: User UUID
        tenant_id: Tenant ID (for isolation)
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Paginated list of user permissions

    Raises:
        ValueError: If user not found
    """
    # Verify user exists in tenant
    user_result = await db.execute(
        GET_USER_BY_ID_QUERY,
        {"user_id": user_id, "tenant_id": tenant_id},
    )
    if not user_result.first():
        raise ValueError(f"User {user_id} not found")

    offset = (page - 1) * page_size

    # Get permissions
    perms_result = await db.execute(
        LIST_USER_PERMISSIONS_QUERY,
        {
            "user_id": user_id,
            "limit": page_size,
            "offset": offset,
        },
    )
    perms_rows = perms_result.mappings().all()
    permissions = [UserPermissionOut(**row) for row in perms_rows]

    # Get total count
    count_result = await db.execute(
        COUNT_USER_PERMISSIONS_QUERY,
        {"user_id": user_id},
    )
    total = count_result.scalar_one()

    return PaginatedResponse[UserPermissionOut](
        data=permissions,
        total=total,
        page=page,
        page_size=page_size,
    )


async def grant_permissions_to_user_service(
    db: AsyncSession,
    user_id: str,
    permission_codes: List[str],
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Grant permissions to a user.

    User will be assigned these permissions.

    Args:
        db: Database session
        user_id: User UUID
        permission_codes: Permission codes (e.g., ["users:read", "users:write"])
        tenant_id: Tenant ID (for isolation)

    Returns:
        A dictionary with the following keys:
            - "granted_count": The number of permissions granted
            - "requested_count": The total number of permissions requested
            - "already_had": The number of permissions already had

    Raises:
        ValueError: If user or permission not found
    """
    try:
        # Verify user exists
        user_result = await db.execute(
            GET_USER_BY_ID_QUERY,
            {"user_id": user_id, "tenant_id": tenant_id},
        )

        user_row = user_result.mappings().first()

        if not user_row:
            raise ValueError(f"User {user_id} not found")

        if user_row["is_root"]:
            raise ValueError("Root users cannot be granted permissions")

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
            GRANT_PERMISSIONS_TO_USER_QUERY,
            {
                "user_id": user_id,
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


async def revoke_permissions_from_user_service(
    db: AsyncSession,
    user_id: str,
    permission_codes: List[str],
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Revoke permissions from a user.

    User will lose these permissions unless they have it assigned as part of a group.

    Args:
        db: Database session
        user_id: User UUID
        permission_codes: Permission codes (e.g., ["users:read", "users:write"])
        tenant_id: Tenant ID (for isolation)

    Returns:
        A dictionary with the following keys:
            - "revoked_count": The number of permissions revoked
            - "requested_count": The total number of permissions requested
            - "not_present": The number of permissions not present

    Raises:
        ValueError: If user not found
    """
    try:
        # Verify user exists
        user_result = await db.execute(
            GET_USER_BY_ID_QUERY,
            {"user_id": user_id, "tenant_id": tenant_id},
        )
        if not user_result.first():
            raise ValueError(f"User {user_id} not found")

        # Delete permissions
        result = await db.execute(
            REVOKE_PERMISSIONS_FROM_USER_QUERY,
            {
                "user_id": user_id,
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


async def add_user_to_group_service(
    db: AsyncSession,
    group_id: str,
    user_id: str,
    tenant_id: str,
) -> Literal[True]:
    """
    Add a user to a group.

    Both the user and group must belong to the same tenant.

    Args:
        db: Database session
        group_id: Group UUID
        user_id: User UUID
        tenant_id: Tenant ID (for isolation)

    Returns:
        True

    Raises:
        ValueError: If user or group not found in tenant
    """
    if not user_id:
        raise ValueError("User ID is required")

    try:
        # Verify group belongs to tenant
        group_result = await db.execute(
            GET_GROUP_BY_ID_QUERY,
            {"group_id": group_id, "tenant_id": tenant_id},
        )
        if not group_result.first():
            raise ValueError(f"Group {group_id} not found")

        # Validate user belongs to tenant
        valid_user_result = await db.execute(
            text("""
                SELECT id, is_root FROM users
                WHERE id = :user_id AND tenant_id = :tenant_id
            """),
            {"user_id": user_id, "tenant_id": tenant_id},
        )

        valid_user = valid_user_result.mappings().first()
        if valid_user is None:
            raise ValueError(f"User {user_id} not found")

        is_root = valid_user["is_root"]
        valid_user_id = valid_user["id"]

        if is_root:
            raise ValueError("Root user cannot be added to a group")

        # Insert valid users
        await db.execute(
            ADD_USER_TO_GROUP_QUERY,
            {"group_id": group_id, "user_id": valid_user_id},
        )

        await db.commit()

        return True

    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to add users to group: {str(e)}") from e


async def remove_user_from_group_service(
    db: AsyncSession,
    group_id: str,
    user_id: str,
    tenant_id: str,
) -> bool:
    """
    Remove user from a group.

    Args:
        db: Database session
        group_id: Group UUID
        user_id: User UUID
        tenant_id: Tenant ID (for isolation)

    Returns:
        Dict with removed + not_found
    """
    if not user_id:
        return False

    try:
        # Verify group belongs to tenant
        group_result = await db.execute(
            GET_GROUP_BY_ID_QUERY,
            {"group_id": group_id, "tenant_id": tenant_id},
        )
        if not group_result.first():
            raise ValueError(f"Group {group_id} not found")

        await db.execute(
            REMOVE_USER_FROM_GROUP_QUERY,
            {"group_id": group_id, "user_id": user_id},
        )

        await db.commit()

        return True

    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to remove users from group: {str(e)}") from e


async def list_user_groups_service(
    db: AsyncSession,
    user_id: str,
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse[GroupOut]:
    """
    List groups a user is a member of.

    Args:
        db: Database session
        user_id: User UUID
        tenant_id: Tenant ID (for isolation)
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Paginated list of groups user is a member of

    Raises:
        ValueError: If user not found
    """
    # Verify user exists in tenant
    user_result = await db.execute(
        GET_USER_BY_ID_QUERY,
        {"user_id": user_id, "tenant_id": tenant_id},
    )
    if not user_result.first():
        raise ValueError(f"User {user_id} not found")

    offset = (page - 1) * page_size

    # Get groups user is a member of
    groups_result = await db.execute(
        LIST_GROUPS_QUERY,
        {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "limit": page_size,
            "offset": offset,
        },
    )
    groups_rows = groups_result.mappings().all()
    groups = [GroupOut(**row) for row in groups_rows]

    # Get total count
    count_result = await db.execute(
        COUNT_USER_MEMBER_GROUPS_QUERY,
        {"user_id": user_id},
    )
    total = count_result.scalar_one()

    return PaginatedResponse[GroupOut](
        data=groups,
        total=total,
        page=page,
        page_size=page_size,
    )
