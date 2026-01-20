from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db, require_permission
from src.permissions.schemas import GrantPermissionRequest, GrantPermissionsRequest
from src.permissions.service import (
    grant_permission,
    grant_permissions_bulk,
    list_user_permissions,
)

permissions_router = APIRouter(prefix="/permissions", tags=["Permissions"])


@permissions_router.get("/me", response_model=list[str])
async def list_my_permissions(
    db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """List all effective permissions for the current user (wildcards resolved)."""
    return await list_user_permissions(db, current_user["user_id"])


@permissions_router.post("/grant", status_code=status.HTTP_200_OK)
async def grant_new_permission(
    request: GrantPermissionRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("permissions:grant")),
):
    """Grant a permission to a user, group, or role."""
    success = await grant_permission(
        db,
        target_type=request.target_type,
        target_id=request.target_id,
        permission_code=request.permission_code,
    )
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to grant permission (invalid code or target)",
        )
    return {"message": "Permission granted"}


@permissions_router.post("/grant/bulk", status_code=status.HTTP_200_OK)
async def grant_permissions_bulk_endpoint(
    request: GrantPermissionsRequest,
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

    success_count = await grant_permissions_bulk(
        db=db,
        target_type=request.target_type,
        target_id=request.target_id,
        permission_codes=request.permission_codes,
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
