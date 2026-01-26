"""
FastAPI routes for group management.

Endpoints:
- POST   /groups              - Create group (requires groups:create)
- GET    /groups              - List groups (requires groups:read)
- GET    /groups/{id}         - Get group details (requires groups:read)
- PATCH  /groups/{id}         - Update group (requires groups:update)
- DELETE /groups/{id}         - Delete group (requires groups:delete)

Member management:
- GET    /groups/{id}/members           - List members (requires groups:read)
- POST   /groups/{id}/members           - Add members (requires groups:update)
- DELETE /groups/{id}/members           - Remove members (requires groups:update)

Permission management:
- GET    /groups/{id}/permissions - List permissions (requires groups:read)
- POST   /groups/{id}/permissions - Grant permission (requires permissions:grant)
- DELETE /groups/{id}/permissions - Revoke permission (requires permissions:revoke)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db, require_permission
from src.core.responses import PaginatedResponse
from src.groups.schemas import (
    AddUsersToGroupRequest,
    GrantPermissionsToGroupRequest,
    GroupCreate,
    GroupDetailOut,
    GroupMemberOut,
    GroupOut,
    GroupPermissionOut,
    GroupUpdate,
    RemoveUsersFromGroupRequest,
    RevokePermissionsFromGroupRequest,
)
from src.groups.service import (
    add_users_to_group_service,
    create_group_service,
    delete_group_service,
    get_group_by_id_service,
    grant_permissions_to_group_service,
    list_group_members_service,
    list_group_permissions_service,
    list_groups_service,
    remove_users_from_group_service,
    revoke_permissions_from_group_service,
    update_group_service,
)

group_router = APIRouter(prefix="/groups", tags=["Groups"])


# =============================================================================
# Group CRUD
# =============================================================================


@group_router.post("/", response_model=GroupOut, status_code=201)
async def create_group(
    group_in: GroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("groups:create")),
):
    """
    Create a new group in the current tenant.

    Requires: groups:create permission

    Group names must be unique within a tenant.
    """
    tenant_id = current_user["tenant_id"]

    try:
        group = await create_group_service(db, group_in, tenant_id)
        return group
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@group_router.get(
    "/", response_model=PaginatedResponse[GroupDetailOut], status_code=200
)
async def list_groups(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("groups:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List all groups in the current tenant.

    Requires: groups:read permission

    Returns paginated list of groups with basic info.
    """
    tenant_id = current_user["tenant_id"]

    try:
        return await list_groups_service(db, tenant_id, page, page_size)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@group_router.get("/{group_id}", response_model=GroupDetailOut, status_code=200)
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("groups:read")),
):
    """
    Get detailed information about a specific group.

    Requires: groups:read permission

    Returns group details including member count and permission count.
    """
    tenant_id = current_user["tenant_id"]

    try:
        group = await get_group_by_id_service(db, group_id, tenant_id)
        return group
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@group_router.patch("/{group_id}", response_model=GroupOut, status_code=200)
async def update_group(
    group_id: str,
    group_update: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("groups:update")),
):
    """
    Update a group's name or description.

    Requires: groups:update permission

    Only provided fields will be updated.
    """
    tenant_id = current_user["tenant_id"]

    try:
        group = await update_group_service(db, group_id, group_update, tenant_id)
        return group
    except ValueError as e:
        # Could be "not found" or "name conflict"
        status_code = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@group_router.delete("/{group_id}", status_code=204)
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("groups:delete")),
):
    """
    Delete a group.

    Requires: groups:delete permission

    This will also remove all group memberships and permissions.
    Users in the group will lose inherited permissions (unless they have them directly).
    """
    tenant_id = current_user["tenant_id"]

    try:
        deleted = await delete_group_service(db, group_id, tenant_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Group not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Member Management
# =============================================================================


@group_router.get(
    "/{group_id}/members",
    response_model=PaginatedResponse[GroupMemberOut],
    status_code=200,
)
async def list_group_members(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("groups:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List all members of a group.

    Requires: groups:read permission

    Returns paginated list of users who are members of this group.
    """
    tenant_id = current_user["tenant_id"]

    try:
        return await list_group_members_service(
            db, group_id, tenant_id, page, page_size
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@group_router.post("/{group_id}/members/add", status_code=201)
async def add_user_to_group(
    group_id: str,
    request: AddUsersToGroupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("groups:update")),
):
    """
    Adds users to a group.

    Requires: groups:update permission

    The users will inherit all permissions assigned to this group.
    Both the users and group must belong to the same tenant.
    """
    tenant_id = current_user["tenant_id"]
    user_ids = [str(user_id) for user_id in request.user_ids]

    try:
        result = await add_users_to_group_service(db, group_id, user_ids, tenant_id)

        return {
            "message": "Group users processed",
            **result,
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@group_router.post("/{group_id}/members/remove", status_code=204)
async def remove_user_from_group(
    group_id: str,
    request: RemoveUsersFromGroupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("groups:update")),
):
    """
    Remove users from a group.

    Requires: groups:update permission

    The users will lose permissions inherited from this group
    (unless they have them assigned directly).
    """
    tenant_id = current_user["tenant_id"]
    user_ids = [str(user_id) for user_id in request.user_ids]

    try:
        result = await remove_users_from_group_service(
            db, group_id, user_ids, tenant_id
        )

        return {
            "message": "Group users processed",
            **result,
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Permission Management
# =============================================================================


@group_router.get(
    "/{group_id}/permissions",
    response_model=PaginatedResponse[GroupPermissionOut],
    status_code=200,
)
async def list_group_permissions(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("groups:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """
    List all permissions assigned to a group.

    Requires: groups:read permission

    Returns paginated list of permissions.
    All group members inherit these permissions.
    """
    tenant_id = current_user["tenant_id"]

    try:
        return await list_group_permissions_service(
            db, group_id, tenant_id, page, page_size
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@group_router.post("/{group_id}/permissions/grant", status_code=201)
async def grant_permissions_to_group(
    group_id: str,
    request: GrantPermissionsToGroupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("permissions:grant")),
):
    """
    Grants permissions to a group.

    Requires: permissions:grant permission

    All members of the group will inherit these permissions.
    """
    tenant_id = current_user["tenant_id"]

    try:
        result = await grant_permissions_to_group_service(
            db, group_id, request.permission_codes, tenant_id
        )

        return {
            "message": "Permissions processed",
            **result,
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@group_router.post("/{group_id}/permissions/revoke", status_code=200)
async def revoke_permissions_from_group(
    group_id: str,
    request: RevokePermissionsFromGroupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("permissions:revoke")),
):
    """
    Revoke permissions from a group.

    Requires: permissions:revoke permission

    Members will lose these permissions unless they have them assigned directly.
    """
    tenant_id = current_user["tenant_id"]

    try:
        result = await revoke_permissions_from_group_service(
            db, group_id, request.permission_codes, tenant_id
        )

        return {
            "message": "Permissions processed",
            **result,
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
