"""
FastAPI router for storefront-product relationship management.
Handles adding, removing, and listing products in storefronts.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db, require_permission
from src.core.responses import PaginatedResponse
from src.storefront_products.schemas import (
    StorefrontProductAdd,
    StorefrontProductBulkAdd,
    StorefrontProductOut,
    StorefrontProductUpdate,
)
from src.storefront_products.service import (
    add_product_to_storefront_service,
    bulk_add_products_to_storefront_service,
    list_storefront_products_service,
    remove_product_from_storefront_service,
    update_storefront_product_service,
)

storefront_products_router = APIRouter(
    prefix="/storefronts/{storefront_id}/products",
    tags=["Storefronts - Product Management"],
)


@storefront_products_router.post(
    "/",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def add_product_to_storefront(
    storefront_id: UUID,
    data: StorefrontProductAdd,
    current_user: dict = Depends(require_permission("storefronts:update")),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a single product to a storefront.

    Requires `storefronts:update` permission.
    """
    try:
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(403, "No tenant associated with user")

        result = await add_product_to_storefront_service(
            db, str(storefront_id), tenant_id, data
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@storefront_products_router.post(
    "/bulk",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_add_products_to_storefront(
    storefront_id: UUID,
    data: StorefrontProductBulkAdd,
    current_user: dict = Depends(require_permission("storefronts:update")),
    db: AsyncSession = Depends(get_db),
):
    """
    Add multiple products to a storefront at once.

    Requires `storefronts:update` permission.
    """
    try:
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(403, "No tenant associated with user")

        result = await bulk_add_products_to_storefront_service(
            db,
            str(storefront_id),
            tenant_id,
            [str(pid) for pid in data.product_ids],
            data.is_visible,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@storefront_products_router.get(
    "/",
    response_model=PaginatedResponse[StorefrontProductOut],
)
async def list_storefront_products(
    storefront_id: UUID,
    current_user: dict = Depends(require_permission("storefronts:read")),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """
    List all products in a storefront with their display settings.

    Requires `storefronts:read` permission.
    """
    try:
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(403, "No tenant associated with user")

        return await list_storefront_products_service(
            db, str(storefront_id), tenant_id, page, page_size
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@storefront_products_router.patch(
    "/{product_id}",
    response_model=dict,
)
async def update_storefront_product(
    storefront_id: UUID,
    product_id: UUID,
    data: StorefrontProductUpdate,
    current_user: dict = Depends(require_permission("storefronts:update")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a product's display settings in a storefront.

    Requires `storefronts:update` permission.
    """
    try:
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(403, "No tenant associated with user")

        result = await update_storefront_product_service(
            db, str(storefront_id), str(product_id), tenant_id, data
        )
        if not result:
            raise HTTPException(
                status_code=404, detail="Product not found in storefront"
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@storefront_products_router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_product_from_storefront(
    storefront_id: UUID,
    product_id: UUID,
    current_user: dict = Depends(require_permission("storefronts:update")),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove a product from a storefront.

    Requires `storefronts:update` permission.
    """
    try:
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(403, "No tenant associated with user")

        success = await remove_product_from_storefront_service(
            db, str(storefront_id), str(product_id), tenant_id
        )
        if not success:
            raise HTTPException(
                status_code=404, detail="Product not found in storefront"
            )
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
