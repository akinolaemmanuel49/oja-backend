"""
Product catalog service layer.
Handles CRUD operations for products and their variants:
- Simple and variable products
- SKU uniqueness enforcement
- Optional variant inclusion in read operations
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.products.schemas import (
    ProductCreate,
    ProductUpdate,
)


async def create_product_service(
    db: AsyncSession, tenant_id: str, data: ProductCreate
) -> Dict[str, Any]:
    """
    Create a new product (simple or variable) including optional variants in a single transaction.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        data: Product creation payload (including variants if variable)

    Returns:
        Dictionary containing created product and any variants

    Raises:
        ValueError: If SKU already exists
        RuntimeError: On creation failure
    """
    try:
        # 1. Insert main product
        product_query = text("""
            INSERT INTO products (
                tenant_id, type, name, description, base_price, sku,
                created_at, updated_at
            )
            VALUES (
                :tenant_id, :type, :name, :description, :base_price, :sku,
                NOW(), NOW()
            )
            RETURNING id, tenant_id, type, name, description, base_price, sku,
                      created_at, updated_at
        """)

        product_result = await db.execute(
            product_query,
            {
                "tenant_id": tenant_id,
                "type": data.type,
                "name": data.name,
                "description": data.description,
                "base_price": data.base_price,
                "sku": data.sku if data.type == "simple" else None,
            },
        )
        product_row = product_result.mappings().first()
        if not product_row:
            raise RuntimeError("Failed to create product")

        product = dict(product_row)
        product_id = product["id"]

        # 2. Insert variants if variable product
        variants = []
        if data.type == "variable" and data.variants:
            variant_query = text("""
                INSERT INTO product_variants (
                    product_id, sku, price, stock_quantity, re_order_level, attributes,
                    created_at, updated_at
                )
                VALUES (
                    :product_id, :sku, :price, :stock_quantity, :re_order_level, :attributes::jsonb,
                    NOW(), NOW()
                )
                RETURNING id, product_id, sku, price, stock_quantity, re_order_level,
                          attributes, created_at, updated_at
            """)

            for variant_data in data.variants:
                result = await db.execute(
                    variant_query,
                    {
                        "product_id": product_id,
                        "sku": variant_data.sku,
                        "price": variant_data.price,
                        "stock_quantity": variant_data.stock_quantity,
                        "re_order_level": variant_data.re_order_level,
                        "attributes": variant_data.attributes or {},
                    },
                )
                variant_row = result.mappings().first()
                if variant_row:
                    variants.append(dict(variant_row))

        product["variants"] = variants
        return product

    except IntegrityError as e:
        if "products_sku_key" in str(e):
            raise ValueError("SKU already exists")
        raise ValueError("Database constraint violation") from e
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to create product: {str(e)}") from e


async def get_product_service(
    db: AsyncSession, product_id: str, tenant_id: str, include_variants: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single product with optional variant details.

    Args:
        db: Database session
        product_id: Product UUID
        tenant_id: Tenant scope
        include_variants: Whether to load variant data

    Returns:
        Product dictionary or None if not found
    """
    product_query = text("""
        SELECT id, tenant_id, type, name, description, base_price, sku,
               created_at, updated_at
        FROM products
        WHERE id = :id AND tenant_id = :tenant_id
    """)

    result = await db.execute(product_query, {"id": product_id, "tenant_id": tenant_id})
    row = result.mappings().first()
    if not row:
        return None

    product = dict(row)

    if include_variants:
        variants_query = text("""
            SELECT id, product_id, sku, price, stock_quantity, re_order_level, attributes,
                   created_at, updated_at
            FROM product_variants
            WHERE product_id = :product_id
            ORDER BY created_at
        """)
        variants_result = await db.execute(variants_query, {"product_id": product_id})
        product["variants"] = [dict(r) for r in variants_result.mappings()]

    return product


async def list_products_service(
    db: AsyncSession,
    tenant_id: str,
    limit: int = 20,
    offset: int = 0,
    include_variants: bool = False,
) -> List[Dict[str, Any]]:
    """
    List products in the tenant with optional variant preloading.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        limit: Maximum number of records
        offset: Pagination offset
        include_variants: Whether to eagerly load variants (can be expensive)

    Returns:
        List of product dictionaries
    """
    query = text("""
        SELECT id, tenant_id, type, name, description, base_price, sku,
               created_at, updated_at
        FROM products
        WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(
        query, {"tenant_id": tenant_id, "limit": limit, "offset": offset}
    )
    products = [dict(row) for row in result.mappings()]

    if include_variants:
        # Optional: batch load variants (can become expensive → consider separate endpoint)
        for p in products:
            v_result = await db.execute(
                text("""
                    SELECT id, sku, price, stock_quantity, re_order_level, attributes
                    FROM product_variants
                    WHERE product_id = :pid
                """),
                {"pid": p["id"]},
            )
            p["variants"] = [dict(r) for r in v_result.mappings()]

    return products


async def update_product_service(
    db: AsyncSession, product_id: str, tenant_id: str, data: ProductUpdate
) -> Optional[Dict[str, Any]]:
    """
    Partially update product fields.

    Args:
        db: Database session
        product_id: Product UUID
        tenant_id: Tenant scope
        data: Fields to update (partial)

    Returns:
        Updated product dictionary or None if not found/no changes

    Raises:
        ValueError: If SKU conflict occurs
    """
    if not any([data.name, data.description, data.base_price, data.sku]):
        return None

    updates = []
    params: Dict[str, Any] = {"id": product_id, "tenant_id": tenant_id}

    if data.name is not None:
        updates.append("name = :name")
        params["name"] = data.name
    if data.description is not None:
        updates.append("description = :description")
        params["description"] = data.description
    if data.base_price is not None:
        updates.append("base_price = :base_price")
        params["base_price"] = data.base_price
    if data.sku is not None:
        updates.append("sku = :sku")
        params["sku"] = data.sku

    query = text(f"""
        UPDATE products
        SET {", ".join(updates)}, updated_at = NOW()
        WHERE id = :id AND tenant_id = :tenant_id
        RETURNING id, tenant_id, type, name, description, base_price, sku,
                  created_at, updated_at
    """)

    try:
        result = await db.execute(query, params)
        row = result.mappings().first()
        return dict(row) if row else None
    except IntegrityError as e:
        if "products_sku_key" in str(e):
            raise ValueError("SKU already exists")
        raise ValueError("Database constraint violation") from e
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to update product: {str(e)}") from e


async def delete_product_service(
    db: AsyncSession, product_id: str, tenant_id: str
) -> bool:
    """
    Hard-delete a product (variants cascade via foreign key).

    Args:
        db: Database session
        product_id: Product UUID
        tenant_id: Tenant scope

    Returns:
        True if product was deleted, False if not found
    """
    result = await db.execute(
        text("""
            DELETE FROM products
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING id
        """),
        {"id": product_id, "tenant_id": tenant_id},
    )
    return result.scalar_one_or_none() is not None
