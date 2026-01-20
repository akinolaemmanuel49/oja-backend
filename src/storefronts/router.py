from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db, require_permission
from src.storefronts.schemas import StorefrontCreate, StorefrontOut, StorefrontUpdate
from src.storefronts.service import (
    create_storefront,
    delete_storefront,
    get_storefront,
    list_storefronts,
    update_storefront,
)

storefront_router = APIRouter(prefix="/storefronts", tags=["Storefronts"])


@storefront_router.post(
    "/", response_model=StorefrontOut, status_code=status.HTTP_201_CREATED
)
async def create_storefront_endpoint(
    data: StorefrontCreate,
    current_user: dict = Depends(require_permission("storefronts:create")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(403, "No tenant associated with user")

    result = await create_storefront(db, tenant_id, data)
    return result


@storefront_router.get("/{storefront_id}", response_model=StorefrontOut)
async def get_storefront_endpoint(
    storefront_id: str,
    current_user: dict = Depends(require_permission("storefronts:read")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(403, "No tenant associated with user")

    result = await get_storefront(db, storefront_id, tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Storefront not found")
    return result


@storefront_router.get("/", response_model=List[StorefrontOut])
async def list_storefronts_endpoint(
    limit: int = 20,
    offset: int = 0,
    current_user: dict = Depends(require_permission("storefronts:read")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(403, "No tenant associated with user")

    return await list_storefronts(db, tenant_id, limit, offset)


@storefront_router.patch("/{storefront_id}", response_model=StorefrontOut)
async def update_storefront_endpoint(
    storefront_id: str,
    data: StorefrontUpdate,
    current_user: dict = Depends(require_permission("storefronts:update")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(403, "No tenant associated with user")

    result = await update_storefront(db, storefront_id, tenant_id, data)
    if not result:
        raise HTTPException(
            status_code=404, detail="Storefront not found or no changes"
        )
    return result


@storefront_router.delete("/{storefront_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_storefront_endpoint(
    storefront_id: str,
    current_user: dict = Depends(require_permission("storefronts:delete")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(403, "No tenant associated with user")

    success = await delete_storefront(db, storefront_id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Storefront not found")
    return None
