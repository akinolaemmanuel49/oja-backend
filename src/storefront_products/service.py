"""
Storefront-Product relationship service layer.
Manages which products appear in which storefronts.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.responses import PaginatedResponse
from src.products.schemas import ProductVariantOut
from src.storefront_products.schemas import (
    StorefrontProductAdd,
    StorefrontProductOut,
    StorefrontProductUpdate,
)

# SQL Queries
INSERT_STOREFRONT_PRODUCT_QUERY = text("""
    INSERT INTO storefront_products (
        storefront_id, product_id, display_order, is_visible, created_at
    )
    VALUES (
        :storefront_id, :product_id, :display_order, :is_visible, NOW()
    )
    RETURNING storefront_id, product_id, display_order, is_visible
""")


GET_STOREFRONT_PRODUCTS_QUERY = text("""
    SELECT
        sp.product_id,
        sp.display_order,
        sp.is_visible,

        p.name            AS product_name,
        p.type            AS product_type,
        p.description     AS product_description,
        p.base_price,
        p.sku,
        p.main_image_url
    FROM storefront_products sp
    INNER JOIN storefronts s ON sp.storefront_id = s.id
    INNER JOIN products p    ON sp.product_id = p.id
    WHERE
        sp.storefront_id = :storefront_id
        AND s.tenant_id = :tenant_id
    ORDER BY sp.display_order ASC, p.name ASC, p.id ASC
    LIMIT :limit OFFSET :offset;
""")

GET_PRODUCT_VARIANTS_FOR_PRODUCTS_QUERY = text("""
    SELECT
        pv.id AS id,
        pv.product_id,
        pv.sku,
        pv.price,
        pv.stock_quantity,
        pv.re_order_level,
        pv.attributes,
        pv.main_image_url,
        pv.image_urls,
        pv.created_at,
        pv.updated_at
    FROM product_variants pv
    WHERE pv.product_id = ANY(:product_ids)
    ORDER BY pv.product_id, pv.id;
""")

COUNT_STOREFRONT_PRODUCTS_QUERY = text("""
    SELECT COUNT(*) 
    FROM storefront_products
    WHERE storefront_id = :storefront_id
""")

UPDATE_STOREFRONT_PRODUCT_QUERY = text("""
    UPDATE storefront_products
    SET display_order = COALESCE(:display_order, display_order),
        is_visible = COALESCE(:is_visible, is_visible)
    WHERE storefront_id = :storefront_id AND product_id = :product_id
    RETURNING storefront_id, product_id, display_order, is_visible
""")

DELETE_STOREFRONT_PRODUCT_QUERY = text("""
    DELETE FROM storefront_products
    WHERE storefront_id = :storefront_id AND product_id = :product_id
    RETURNING product_id
""")

# Query to check if storefront belongs to tenant
VERIFY_STOREFRONT_TENANT_QUERY = text("""
    SELECT id FROM storefronts
    WHERE id = :storefront_id AND tenant_id = :tenant_id
""")

# Query to check if product belongs to tenant
VERIFY_PRODUCT_TENANT_QUERY = text("""
    SELECT id FROM products
    WHERE id = :product_id AND tenant_id = :tenant_id
""")


async def add_product_to_storefront_service(
    db: AsyncSession,
    storefront_id: str,
    tenant_id: str,
    data: StorefrontProductAdd,
) -> Dict[str, Any]:
    """
    Add a product to a storefront.

    Args:
        db: Database session
        storefront_id: Storefront UUID
        tenant_id: Tenant identifier (for authorization)
        data: Product addition data

    Returns:
        Dictionary with storefront-product relationship details

    Raises:
        ValueError: If storefront or product not found, or already linked
        RuntimeError: On database errors
    """
    try:
        # Verify storefront belongs to tenant
        storefront_check = await db.execute(
            VERIFY_STOREFRONT_TENANT_QUERY,
            {"storefront_id": storefront_id, "tenant_id": tenant_id},
        )
        if not storefront_check.scalar_one_or_none():
            raise ValueError("Storefront not found or access denied")

        # Verify product belongs to tenant
        product_check = await db.execute(
            VERIFY_PRODUCT_TENANT_QUERY,
            {"product_id": str(data.product_id), "tenant_id": tenant_id},
        )
        if not product_check.scalar_one_or_none():
            raise ValueError("Product not found or access denied")

        # Add the relationship
        result = await db.execute(
            INSERT_STOREFRONT_PRODUCT_QUERY,
            {
                "storefront_id": storefront_id,
                "product_id": str(data.product_id),
                "display_order": data.display_order,
                "is_visible": data.is_visible,
            },
        )

        row = result.mappings().first()
        if not row:
            raise RuntimeError("Failed to add product to storefront")

        return dict(row)

    except IntegrityError as e:
        if "storefront_products_pkey" in str(e):
            raise ValueError("Product is already in this storefront")
        raise ValueError("Database constraint violation") from e
    except ValueError:
        raise  # Re-raise our custom validation errors
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to add product to storefront: {str(e)}") from e


async def list_storefront_products_service(
    db: AsyncSession,
    storefront_id: str,
    tenant_id: str,
    page: int = 1,
    page_size: int = 50,
) -> PaginatedResponse[StorefrontProductOut]:
    """
    List all products in a storefront.

    Args:
        db: Database session
        storefront_id: Storefront UUID
        tenant_id: Tenant identifier (for authorization)
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Paginated list of products with storefront-specific settings

    Raises:
        ValueError: If storefront not found
    """
    # Verify storefront belongs to tenant
    storefront_check = await db.execute(
        VERIFY_STOREFRONT_TENANT_QUERY,
        {"storefront_id": storefront_id, "tenant_id": tenant_id},
    )
    if not storefront_check.scalar_one_or_none():
        raise ValueError("Storefront not found or access denied")

    offset = (page - 1) * page_size

    # Fetch paginated products
    product_result = await db.execute(
        GET_STOREFRONT_PRODUCTS_QUERY,
        {
            "storefront_id": storefront_id,
            "tenant_id": tenant_id,
            "limit": page_size,
            "offset": offset,
        },
    )

    product_rows = list(product_result.mappings())
    if not product_rows:
        return PaginatedResponse(
            data=[],
            total=0,
            page=page,
            page_size=page_size,
        )

    # Build product map
    products_by_id: dict[UUID, StorefrontProductOut] = {}
    product_ids: list[UUID] = []

    for row in product_rows:
        product = StorefrontProductOut(
            **row,
            variants=[],
        )
        products_by_id[product.product_id] = product
        product_ids.append(product.product_id)

    # Fetch variants in one query
    variant_result = await db.execute(
        GET_PRODUCT_VARIANTS_FOR_PRODUCTS_QUERY,
        {"product_ids": product_ids},
    )

    for row in variant_result.mappings():
        products_by_id[row["product_id"]].variants.append(ProductVariantOut(**row))

    # Total count (product-level)
    count_result = await db.execute(
        COUNT_STOREFRONT_PRODUCTS_QUERY,
        {
            "storefront_id": storefront_id,
        },
    )
    total = count_result.scalar_one()

    return PaginatedResponse(
        data=list(products_by_id.values()),
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_storefront_product_service(
    db: AsyncSession,
    storefront_id: str,
    product_id: str,
    tenant_id: str,
    data: StorefrontProductUpdate,
) -> Optional[Dict[str, Any]]:
    """
    Update a product's settings in a storefront.

    Args:
        db: Database session
        storefront_id: Storefront UUID
        product_id: Product UUID
        tenant_id: Tenant identifier (for authorization)
        data: Update data

    Returns:
        Updated relationship data or None if not found

    Raises:
        ValueError: If storefront not found
        RuntimeError: On database errors
    """
    try:
        # Verify storefront belongs to tenant
        storefront_check = await db.execute(
            VERIFY_STOREFRONT_TENANT_QUERY,
            {"storefront_id": storefront_id, "tenant_id": tenant_id},
        )
        if not storefront_check.scalar_one_or_none():
            raise ValueError("Storefront not found or access denied")

        # Update the relationship
        result = await db.execute(
            UPDATE_STOREFRONT_PRODUCT_QUERY,
            {
                "storefront_id": storefront_id,
                "product_id": product_id,
                "display_order": data.display_order,
                "is_visible": data.is_visible,
            },
        )

        row = result.mappings().first()
        return dict(row) if row else None

    except ValueError:
        raise
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to update product in storefront: {str(e)}") from e


async def remove_product_from_storefront_service(
    db: AsyncSession,
    storefront_id: str,
    product_id: str,
    tenant_id: str,
) -> bool:
    """
    Remove a product from a storefront.

    Args:
        db: Database session
        storefront_id: Storefront UUID
        product_id: Product UUID
        tenant_id: Tenant identifier (for authorization)

    Returns:
        True if removed, False if not found

    Raises:
        ValueError: If storefront not found
    """
    # Verify storefront belongs to tenant
    storefront_check = await db.execute(
        VERIFY_STOREFRONT_TENANT_QUERY,
        {"storefront_id": storefront_id, "tenant_id": tenant_id},
    )
    if not storefront_check.scalar_one_or_none():
        raise ValueError("Storefront not found or access denied")

    result = await db.execute(
        DELETE_STOREFRONT_PRODUCT_QUERY,
        {"storefront_id": storefront_id, "product_id": product_id},
    )

    return result.scalar_one_or_none() is not None


async def bulk_add_products_to_storefront_service(
    db: AsyncSession,
    storefront_id: str,
    tenant_id: str,
    product_ids: List[str],
    is_visible: bool = True,
) -> Dict[str, Any]:
    """
    Add multiple products to a storefront at once.

    Args:
        db: Database session
        storefront_id: Storefront UUID
        tenant_id: Tenant identifier
        product_ids: List of product UUIDs to add
        is_visible: Whether products should be visible

    Returns:
        Dictionary with success count and any errors

    Raises:
        ValueError: If storefront not found
    """
    # Verify storefront belongs to tenant
    storefront_check = await db.execute(
        VERIFY_STOREFRONT_TENANT_QUERY,
        {"storefront_id": storefront_id, "tenant_id": tenant_id},
    )
    if not storefront_check.scalar_one_or_none():
        raise ValueError("Storefront not found or access denied")

    added = 0
    skipped = 0
    errors = []

    for idx, product_id in enumerate(product_ids):
        try:
            # Verify product belongs to tenant
            product_check = await db.execute(
                VERIFY_PRODUCT_TENANT_QUERY,
                {"product_id": product_id, "tenant_id": tenant_id},
            )
            if not product_check.scalar_one_or_none():
                errors.append(f"Product {product_id} not found")
                skipped += 1
                continue

            # Add the relationship
            await db.execute(
                INSERT_STOREFRONT_PRODUCT_QUERY,
                {
                    "storefront_id": storefront_id,
                    "product_id": product_id,
                    "display_order": idx,  # Use index as default display order
                    "is_visible": is_visible,
                },
            )
            added += 1

        except IntegrityError:
            # Already exists, skip
            skipped += 1
        except Exception as e:
            errors.append(f"Error adding product {product_id}: {str(e)}")
            skipped += 1

    return {
        "added": added,
        "skipped": skipped,
        "total": len(product_ids),
        "errors": errors if errors else None,
    }
