from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db, require_permission
from src.storefronts.schemas import StorefrontCreate, StorefrontOut, StorefrontUpdate
from src.storefronts.service import (
    create_storefront_service,
    delete_storefront_service,
    get_storefront_service,
    list_storefronts_service,
    update_storefront_service,
)

storefront_router = APIRouter(prefix="/storefronts", tags=["Storefronts - Management"])


@storefront_router.post(
    "/", response_model=StorefrontOut, status_code=status.HTTP_201_CREATED
)
async def create_storefront(
    data: StorefrontCreate,
    current_user: dict = Depends(require_permission("storefronts:create")),
    db: AsyncSession = Depends(get_db),
):
    try:
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(403, "No tenant associated with user")

        result = await create_storefront_service(db, tenant_id, data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Failed to create storefront")


@storefront_router.get("/{storefront_id}", response_model=StorefrontOut)
async def get_storefront(
    storefront_id: str,
    current_user: dict = Depends(require_permission("storefronts:read")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(403, "No tenant associated with user")

    result = await get_storefront_service(db, storefront_id, tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Storefront not found")
    return result


@storefront_router.get("/", response_model=List[StorefrontOut])
async def list_storefronts(
    current_user: dict = Depends(require_permission("storefronts:read")),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(403, "No tenant associated with user")

    return await list_storefronts_service(db, tenant_id, page, page_size)


@storefront_router.patch("/{storefront_id}", response_model=StorefrontOut)
async def update_storefront(
    storefront_id: str,
    data: StorefrontUpdate,
    current_user: dict = Depends(require_permission("storefronts:update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(403, "No tenant associated with user")

        result = await update_storefront_service(db, storefront_id, tenant_id, data)
        if not result:
            raise HTTPException(
                status_code=404, detail="Storefront not found or no changes"
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Failed to update storefront")


@storefront_router.delete("/{storefront_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_storefront(
    storefront_id: str,
    current_user: dict = Depends(require_permission("storefronts:delete")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(403, "No tenant associated with user")

    success = await delete_storefront_service(db, storefront_id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Storefront not found")
    return None
