from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db, require_permission
from src.core.responses import PaginatedResponse
from src.products.schemas import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from src.products.service import (
    create_product_service,
    delete_product_service,
    get_product_service,
    list_products_service,
    update_product_service,
)

products_router = APIRouter(prefix="/products", tags=["Products – Management"])


@products_router.post(
    "/",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product (with optional variants)",
)
async def create_product(
    data: ProductCreate,
    current_user: dict = Depends(require_permission("products:create")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a product for the authenticated user's tenant.
    - Simple products: optional SKU + base_price
    - Variable products: must include at least one variant
    """
    try:
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=403, detail="No tenant associated with user"
            )

        result = await create_product_service(db, tenant_id, data)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@products_router.get(
    "/{product_id}", response_model=ProductOut, summary="Get a single product by ID"
)
async def get_product(
    product_id: UUID,
    current_user: dict = Depends(require_permission("products:read")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with user")

    result = await get_product_service(
        db, str(product_id), tenant_id, include_variants=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Product not found")

    return result


@products_router.get(
    "/",
    response_model=PaginatedResponse[ProductOut],
    summary="List all products for the tenant (paginated)",
)
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_permission("products:read")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with user")

    return await list_products_service(
        db,
        tenant_id,
        page,
        page_size,
        include_variants=True,
    )


@products_router.patch(
    "/{product_id}",
    response_model=ProductOut,
    summary="Update product fields (partial update)",
)
async def update_product(
    product_id: UUID,
    data: ProductUpdate,
    current_user: dict = Depends(require_permission("products:update")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with user")

    try:
        result = await update_product_service(db, str(product_id), tenant_id, data)
        if not result:
            raise HTTPException(
                status_code=404, detail="Product not found or no fields were updated"
            )
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@products_router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product (hard delete)",
)
async def delete_product(
    product_id: UUID,
    current_user: dict = Depends(require_permission("products:delete")),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with user")

    success = await delete_product_service(db, str(product_id), tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")

    return None
