from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db, require_permission
from src.permissions.schemas import PermissionRequest, PermissionsRequest
from src.permissions.service import (
    grant_multiple_permissions,
    grant_single_permission,
    list_user_permissions,
    revoke_multiple_permissions,
    revoke_single_permission,
    tenancy_check,
)

permissions_router = APIRouter(prefix="/permissions", tags=["Permissions"])


@permissions_router.get("/me", response_model=list[str])
async def list_my_permissions(
    db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """List all effective permissions for the current user (wildcards resolved)."""
    return await list_user_permissions(db, current_user["user_id"])


@permissions_router.post("/grant", status_code=status.HTTP_200_OK)
async def grant_permission(
    request: PermissionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("permissions:grant")),
):
    """Grant a permission to a user, group, or role."""
    origin_id = current_user["user_id"]
    origin_type = "user"
    destination_id = request.target_id
    destination_type = request.target_type
    is_valid = await tenancy_check(
        db,
        origin_id=origin_id,
        origin_type=origin_type,
        destination_id=destination_id,
        destination_type=destination_type,
    )

    if not is_valid:
        raise HTTPException(status_code=403, detail="Permission denied")
    try:
        success = await grant_single_permission(
            db,
            target_type=request.target_type,
            target_id=request.target_id,
            permission_code=request.permission_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Failed to grant permission (invalid code or target)",
        )
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to grant permission (invalid code or target)",
        )
    return {"message": "Permission granted"}


@permissions_router.post("/grant/bulk", status_code=status.HTTP_200_OK)
async def grant_permissions_bulk(
    request: PermissionsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("permissions:grant")),
):
    """
    Grant multiple permissions to a target (user, group, or role) in one request.
    All assignments are atomic (transaction).
    """
    if not request.permission_codes:
        raise HTTPException(
            status_code=400, detail="At least one permission code required"
        )

    origin_id = current_user["user_id"]
    origin_type = "user"
    destination_id = request.target_id
    destination_type = request.target_type
    is_valid = await tenancy_check(
        db,
        origin_id=origin_id,
        origin_type=origin_type,
        destination_id=destination_id,
        destination_type=destination_type,
    )
    if not is_valid:
        raise HTTPException(status_code=403, detail="Permission denied")

    try:
        success_count = await grant_multiple_permissions(
            db=db,
            target_type=request.target_type,
            target_id=request.target_id,
            permission_codes=request.permission_codes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Failed to grant permission (invalid code or target)",
        )

    if success_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No valid permissions granted (invalid codes or target)",
        )

    return {
        "message": f"Successfully granted {success_count} permission(s)",
        "granted": success_count,
        "requested": len(request.permission_codes),
    }


@permissions_router.post("/revoke", status_code=status.HTTP_200_OK)
async def revoke_permission(
    request: PermissionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("permissions:revoke")),
):
    origin_id = current_user["user_id"]
    origin_type = "user"
    destination_id = request.target_id
    destination_type = request.target_type
    is_valid = await tenancy_check(
        db,
        origin_id=origin_id,
        origin_type=origin_type,
        destination_id=destination_id,
        destination_type=destination_type,
    )
    if not is_valid:
        raise HTTPException(status_code=403, detail="Permission denied")
    """Revoke a permission from a user, group, or role."""
    try:
        success = await revoke_single_permission(
            db,
            target_type=request.target_type,
            target_id=request.target_id,
            permission_code=request.permission_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Failed to revoke permission (invalid code or target)",
        )
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to revoke permission (invalid code or target)",
        )
    return {"message": "Permission revoked"}


@permissions_router.post("/revoke/bulk", status_code=status.HTTP_200_OK)
async def revoke_permissions_bulk(
    request: PermissionsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("permissions:revoke")),
):
    """
    Grant multiple permissions to a target (user, group, or role) in one request.
    All assignments are atomic (transaction).
    """
    if not request.permission_codes:
        raise HTTPException(
            status_code=400, detail="At least one permission code required"
        )

    origin_id = current_user["user_id"]
    origin_type = "user"
    destination_id = request.target_id
    destination_type = request.target_type
    is_valid = await tenancy_check(
        db,
        origin_id=origin_id,
        origin_type=origin_type,
        destination_id=destination_id,
        destination_type=destination_type,
    )
    if not is_valid:
        raise HTTPException(status_code=403, detail="Permission denied")

    try:
        success_count = await revoke_multiple_permissions(
            db=db,
            target_type=request.target_type,
            target_id=request.target_id,
            permission_codes=request.permission_codes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Failed to revoke permission (invalid code or target)",
        )

    if success_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No valid permissions revoked (invalid codes or target)",
        )

    return {
        "message": f"Successfully revoked {success_count} permission(s)",
        "granted": success_count,
        "requested": len(request.permission_codes),
    }
