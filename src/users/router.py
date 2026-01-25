"""
FastAPI routes for user management.

Endpoints:
- POST   /users              - Create user (requires users:create)
- POST   /users/root         - Create root user (only one per tenant)
- GET    /users              - List users (requires users:read)
- GET    /users/{id}         - Get user details (requires users:read)
- PATCH  /users/{id}         - Update user (requires users:update)
- DELETE /users/{id}         - Delete user (requires users:delete)

Permission management:
- GET    /users/{id}/permissions - List permissions (requires users:read)
- POST   /users/{id}/permissions - Grant permission (requires permissions:grant)
- DELETE /users/{id}/permissions - Revoke permission (requires permissions:revoke)

Group management:
- GET    /users/{id}/groups - List groups user is a member of (requires users:read)
- POST   /users/{id}/groups - Add user to group (requires groups:manage)
- DELETE /users/{id}/groups - Remove user from group (requires groups:manage)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db, require_permission
from src.core.responses import PaginatedResponse
from src.groups.schemas import GroupOut
from src.users.schemas import (
    AddUserToGroupRequest,
    GrantPermissionsToUserRequest,
    RemoveUserFromGroupRequest,
    RevokePermissionsFromUserRequest,
    UserCreate,
    UserOut,
    UserPermissionOut,
    UserUpdate,
)
from src.users.service import (
    add_user_to_group_service,
    create_user_service,
    delete_user_service,
    get_user_by_id_service,
    get_users_service,
    grant_permissions_to_user_service,
    list_user_groups_service,
    list_user_permissions_service,
    remove_user_from_group_service,
    revoke_permissions_from_user_service,
    update_user_service,
)

user_router = APIRouter(prefix="/users", tags=["Users"])


@user_router.post("/root", response_model=UserOut, status_code=201)
async def create_root_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await create_user_service(db, user_in, is_root=True, tenant_id=None)
        user = result["user"]

        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Failed to create user")


@user_router.post("/", response_model=UserOut, status_code=201)
async def create_regular_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("users:create")),
):
    tenant_id = current_user["tenant_id"]

    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant ID is required")
    try:
        result = await create_user_service(
            db, user_in, is_root=False, tenant_id=tenant_id
        )
        user = result["user"]

        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Failed to create user")


@user_router.get("/{user_id}", response_model=UserOut, status_code=200)
async def get_user_by_id(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("users:read")),
):
    try:
        result = await get_user_by_id_service(user_id, db)
        user = result["user"]

        return user
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@user_router.get("/", response_model=PaginatedResponse, status_code=200)
async def get_users(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("users:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    tenant_id = current_user["tenant_id"]

    try:
        return await get_users_service(tenant_id, db, page, page_size)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@user_router.patch("/{user_id}", response_model=UserOut, status_code=200)
async def update_user(
    user_id: str,
    update_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("users:update")),
):
    """
    Update a user's information.
    Requires users:update permission.
    """
    tenant_id = current_user["tenant_id"]

    try:
        result = await update_user_service(db, user_id, tenant_id, update_data)
        return result["user"]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@user_router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("users:delete")),
):
    """
    Delete a user (soft delete).
    Requires users:delete permission.
    """
    tenant_id = current_user["tenant_id"]
    current_user_id = current_user["user_id"]

    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Cannot delete self")

    try:
        deleted = await delete_user_service(db, user_id, tenant_id)

        if not deleted:
            raise ValueError("User not found or cannot be deleted")

        return None

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Permission Management
# =============================================================================


@user_router.get(
    "/{user_id}/permissions",
    response_model=PaginatedResponse[UserPermissionOut],
    status_code=200,
)
async def list_user_permissions(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("users:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """
    List all permissions assigned to a user.

    Requires: users:read permission

    Returns paginated list of permissions.
    """
    tenant_id = current_user["tenant_id"]

    try:
        return await list_user_permissions_service(
            db, user_id, tenant_id, page, page_size
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@user_router.post("/{user_id}/permissions/grant", status_code=201)
async def grant_permissions_to_user(
    user_id: str,
    request: GrantPermissionsToUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("permissions:grant")),
):
    """
    Grants permissions to a user.

    Requires: permissions:grant permission

    Assign permissions to a user.
    """
    tenant_id = current_user["tenant_id"]

    try:
        result = await grant_permissions_to_user_service(
            db, user_id, request.permission_codes, tenant_id
        )

        return {
            "message": "Permissions processed",
            **result,
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@user_router.post("/{user_id}/permissions/revoke", status_code=200)
async def revoke_permissions_from_user(
    user_id: str,
    request: RevokePermissionsFromUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("permissions:revoke")),
):
    """
    Revoke permissions from a user.

    Requires: permissions:revoke permission

    User loses these permissions unless they have them assigned as part of a group.
    """
    tenant_id = current_user["tenant_id"]

    try:
        result = await revoke_permissions_from_user_service(
            db, user_id, request.permission_codes, tenant_id
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


# =============================================================================
# Groups Management
# =============================================================================
@user_router.post("/{user_id}/groups", status_code=201)
async def add_user_to_group(
    user_id: str,
    request: AddUserToGroupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("permissions:grant")),
):
    """
    Adds a user to a group.

    Requires: groups:update permission

    Assign a user to a group.
    """
    tenant_id = current_user["tenant_id"]
    group_id = str(request.group_id)

    try:
        result = await add_user_to_group_service(db, group_id, user_id, tenant_id)

        if result:
            return {
                "message": "User added to group",
            }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@user_router.delete("/{user_id}/groups", status_code=200)
async def remove_user_from_group(
    user_id: str,
    request: RemoveUserFromGroupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("permissions:revoke")),
):
    """
    Removes a user from a group.

    Requires: groups:update permission

    Removes a user from a group.
    """
    tenant_id = current_user["tenant_id"]
    group_id = str(request.group_id)

    try:
        result = await remove_user_from_group_service(db, group_id, user_id, tenant_id)

        if result:
            return {
                "message": "User removed from group",
            }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@user_router.get(
    "/{user_id}/groups",
    response_model=PaginatedResponse[GroupOut],
    status_code=200,
)
async def list_user_groups(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=Depends(require_permission("groups:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List all groups that the user is a member of.

    Requires: groups:read permission

    Returns paginated list of groups that the user is a member of.
    """
    tenant_id = current_user["tenant_id"]

    try:
        return await list_user_groups_service(db, user_id, tenant_id, page, page_size)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
