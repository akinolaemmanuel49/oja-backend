"""
Product catalog service layer.
Handles CRUD operations for products and their variants:
- Simple and variable products
- SKU uniqueness enforcement
- Optional variant inclusion in read operations
- Image URL management (main_image_url + image_urls)
- Optional storefront assignment during creation
"""

import json
from decimal import Decimal
from itertools import product as cartesian_product
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.responses import PaginatedResponse
from src.products.schemas import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    VariantOptionInput,
)
from src.products.utils import normalize_attributes, normalize_image_urls

# ─────────────────────────────────────────────────────────────────────────────
# SQL Query Definitions
# ─────────────────────────────────────────────────────────────────────────────
INSERT_PRODUCT_QUERY = text("""
    INSERT INTO products (
        tenant_id, type, name, description, base_price, sku,
        stock_quantity, re_order_level, main_image_url, image_urls,
        created_at, updated_at
    )
    VALUES (
        :tenant_id, :type, :name, :description, :base_price, :sku,
        :stock_quantity, :re_order_level, :main_image_url, :image_urls,
        NOW(), NOW()
    )
    RETURNING id, tenant_id, type, name, description, base_price, sku,
              stock_quantity, re_order_level, main_image_url, image_urls,
              created_at, updated_at
""")

INSERT_VARIANT_PRODUCT_QUERY = text("""
    INSERT INTO product_variants (
        product_id, sku, price, stock_quantity, re_order_level, attributes,
        main_image_url, image_urls, created_at, updated_at
    )
    VALUES (
        :product_id, :sku, :price, :stock_quantity, :re_order_level, :attributes,
        :main_image_url, :image_urls, NOW(), NOW()
    )
    RETURNING id, product_id, sku, price, stock_quantity, re_order_level,
              attributes, main_image_url, image_urls, created_at, updated_at
""").bindparams(attributes=bindparam("attributes", type_=JSONB))

# Link a product to a storefront (optional during creation)
INSERT_STOREFRONT_PRODUCT_LINK_QUERY = text("""
    INSERT INTO storefront_products (
        storefront_id, product_id, display_order, is_visible, created_at
    )
    VALUES (
        :storefront_id, :product_id, :display_order, :is_visible, NOW()
    )
    ON CONFLICT (storefront_id, product_id) DO NOTHING
""")

GET_PRODUCT_QUERY = text("""
    SELECT id, tenant_id, type, name, description, base_price, sku,
           stock_quantity, re_order_level, main_image_url, image_urls,
           created_at, updated_at
    FROM products
    WHERE id = :id AND tenant_id = :tenant_id
""")

GET_VARIANT_PRODUCT_QUERY = text("""
    SELECT id, product_id, sku, price, stock_quantity, re_order_level, attributes,
           main_image_url, image_urls, created_at, updated_at
    FROM product_variants
    WHERE product_id = :product_id
    ORDER BY created_at
""")

LIST_PRODUCTS_QUERY = text("""
    SELECT id, tenant_id, type, name, description, base_price, sku,
           main_image_url, image_urls, created_at, updated_at
    FROM products
    WHERE tenant_id = :tenant_id
    ORDER BY created_at DESC
    LIMIT :limit OFFSET :offset
""")

COUNT_PRODUCTS_QUERY = text("""
    SELECT COUNT(*)
    FROM products
    WHERE tenant_id = :tenant_id
""")


# ─────────────────────────────────────────────────────────────────────────────
# Service Functions
# ─────────────────────────────────────────────────────────────────────────────
async def create_product_service(
    db: AsyncSession,
    tenant_id: str,
    data: ProductCreate,
    storefront_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new product (simple or variable) with optional layered variants in a single transaction.
    For variable products, generates combinations from variant_options if provided; falls back to explicit variants.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        data: Product creation payload (variants or variant_options for variable)
        storefront_id: Optional storefront UUID to link the product to immediately after creation

    Returns:
        Dictionary containing created product and variants

    Raises:
        ValueError: On validation errors (e.g., missing options, SKU conflicts)
        RuntimeError: On creation failure
    """

    try:
        # ── Prepare main product row ──
        is_simple = data.type == "simple"

        product_params = {
            "tenant_id": tenant_id,
            "type": data.type,
            "name": data.name,
            "description": data.description,
            # Simple products use the 'simple' nested field; variable products have None
            "base_price": data.simple.base_price if is_simple and data.simple else None,
            "sku": data.simple.sku if is_simple and data.simple else None,
            "stock_quantity": data.simple.stock_quantity
            if is_simple and data.simple
            else None,
            "re_order_level": data.simple.re_order_level
            if is_simple and data.simple
            else None,
            # Image URLs - convert HttpUrl to string or use empty defaults
            "main_image_url": str(data.main_image_url) if data.main_image_url else None,
            "image_urls": normalize_image_urls(data.image_urls),
        }

        # Execute product insertion
        result = await db.execute(INSERT_PRODUCT_QUERY, product_params)
        product_row = result.mappings().first()
        if not product_row:
            raise RuntimeError("Product insert returned no row")

        product = dict(product_row)
        product_id = product["id"]

        # ── Handle variable product variants ──
        variants: List[Dict[str, Any]] = []

        if not is_simple:
            # Strategy 1: Generate variants from variant_options (Cartesian product approach)
            if data.variant_options:
                opts: VariantOptionInput = data.variant_options
                if not opts.options:
                    raise ValueError(
                        "variant_options.options cannot be empty for variable products"
                    )

                # Extract attribute keys and their value lists for Cartesian product
                # This creates all possible combinations (e.g., color=[Red,Blue] × size=[S,M,L] = 6 variants)
                attr_keys = list(opts.options.keys())
                attr_values_lists = list(opts.options.values())

                # Default price fallback
                default_price = (
                    opts.price if opts.price is not None else Decimal("0.00")
                )

                # Generate all combinations using itertools.product (Cartesian product)
                # Example: [("Red", "S"), ("Red", "M"), ("Red", "L"), ("Blue", "S"), ...]
                for combination in cartesian_product(*attr_values_lists):
                    # Build attribute dict: {"color": "Red", "size": "S"}
                    attributes = dict(zip(attr_keys, combination))

                    # Auto-generate SKU from attribute values: "Red-S"
                    sku = "-".join(combination)
                    if opts.sku_prefix:
                        sku = f"{opts.sku_prefix}-{sku}"

                    # Prepare variant insertion parameters
                    variant_params = {
                        "product_id": product_id,
                        "sku": sku,
                        "price": default_price,
                        "stock_quantity": opts.stock_quantity,
                        "re_order_level": opts.re_order_level,
                        "attributes": normalize_attributes(attributes),
                        # Image URLs default to None/empty for auto-generated variants
                        "main_image_url": None,
                        "image_urls": [],
                    }

                    # Insert variant
                    res = await db.execute(INSERT_VARIANT_PRODUCT_QUERY, variant_params)
                    variant = res.mappings().first()
                    if variant:
                        variants.append(dict(variant))

            # Strategy 2: Use explicitly provided variants
            elif data.variants:
                for v in data.variants:
                    variant_params = {
                        "product_id": product_id,
                        "sku": v.sku,
                        "price": v.price,
                        "stock_quantity": v.stock_quantity,
                        "re_order_level": v.re_order_level,
                        "attributes": normalize_attributes(v.attributes),
                        # Handle variant-specific images
                        "main_image_url": str(v.main_image_url)
                        if v.main_image_url
                        else None,
                        "image_urls": normalize_image_urls(v.image_urls),
                    }
                    res = await db.execute(INSERT_VARIANT_PRODUCT_QUERY, variant_params)
                    variant = res.mappings().first()
                    if variant:
                        variants.append(dict(variant))

            # Validation: Variable products must have at least one variant
            if not variants:
                raise ValueError(
                    "Variable product must have at least one variant (via variants or variant_options)"
                )

        # ── Optional storefront linking ──
        # If a storefront_id is provided, link the product to that storefront immediately
        if storefront_id:
            link_params = {
                "storefront_id": storefront_id,
                "product_id": product_id,
                "display_order": 0,  # Default display order
                "is_visible": True,  # Default visibility
            }
            await db.execute(INSERT_STOREFRONT_PRODUCT_LINK_QUERY, link_params)

        # ── Assemble response ──
        product["variants"] = variants
        return product

    except IntegrityError as e:
        # Handle unique constraint violations (SKU conflicts, attribute duplicates)
        if any(
            k in str(e)
            for k in [
                "products_sku_key",
                "product_variants_sku_key",
                "product_variants_attributes_key",
            ]
        ):
            raise ValueError("SKU or attribute combination already exists")
        raise
    except Exception as e:
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
    result = await db.execute(
        GET_PRODUCT_QUERY, {"id": product_id, "tenant_id": tenant_id}
    )
    row = result.mappings().first()
    if not row:
        return None

    product = dict(row)

    # Optionally load variants for variable products
    if include_variants:
        variants_result = await db.execute(
            GET_VARIANT_PRODUCT_QUERY, {"product_id": product_id}
        )
        product["variants"] = [dict(r) for r in variants_result.mappings()]

    return product


async def list_products_service(
    db: AsyncSession,
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
    include_variants: bool = False,
) -> PaginatedResponse[ProductOut]:
    """
    List products in the tenant with optional variant preloading.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        page: Page number (1-indexed)
        page_size: Items per page
        include_variants: Whether to eagerly load variants (can be expensive for large catalogs)

    Returns:
        Paginated list of products
    """
    offset = (page - 1) * page_size

    # Get total count first for pagination metadata
    count_result = await db.execute(
        COUNT_PRODUCTS_QUERY,
        {"tenant_id": tenant_id},
    )
    total = count_result.scalar_one()

    # Get products for current page
    result = await db.execute(
        LIST_PRODUCTS_QUERY,
        {"tenant_id": tenant_id, "limit": page_size, "offset": offset},
    )

    products = []
    for row in result.mappings():
        product_data = dict(row)

        # Optionally load variants (N+1 query warning: can be expensive)
        if include_variants:
            variants_result = await db.execute(
                GET_VARIANT_PRODUCT_QUERY,
                {"product_id": product_data["id"]},
            )
            variants = [dict(r) for r in variants_result.mappings()]
            product_data["variants"] = variants

        # Convert to Pydantic model
        product = ProductOut(**product_data)
        products.append(product)

    return PaginatedResponse(
        data=products,
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_product_service(
    db: AsyncSession, product_id: str, tenant_id: str, data: ProductUpdate
) -> Optional[Dict[str, Any]]:
    """
    Partially update product fields, handle type switching with data migration,
    and manage variant additions/removals/updates.

    Args:
        db: Database session
        product_id: Product UUID
        tenant_id: Tenant scope
        data: Fields to update (partial; include variants_to_add, variants_to_remove, variants_to_update)

    Returns:
        Updated product dictionary with variants or None if not found/no changes

    Raises:
        ValueError: On validation errors (e.g., SKU conflicts, invalid switch)
        RuntimeError: On update failure
    """

    try:
        # Fetch current product state
        current = await get_product_service(
            db, product_id, tenant_id, include_variants=True
        )
        if not current:
            return None

        new_type = data.type or current["type"]
        is_now_simple = new_type == "simple"

        # ── Type switch handling (simple ↔ variable conversion) ──
        if new_type != current["type"]:
            if is_now_simple:
                # Converting variable → simple: migrate first variant's data
                if not current.get("variants"):
                    raise ValueError(
                        "Cannot switch to simple: no variants to migrate from"
                    )
                first = current["variants"][0]
                # Populate simple product fields from first variant
                data.sku = data.sku or first["sku"]
                data.base_price = data.base_price or first["price"]
                data.stock_quantity = data.stock_quantity or first["stock_quantity"]
                data.re_order_level = data.re_order_level or first["re_order_level"]
                # Delete all variants since we're now simple
                await db.execute(
                    text("DELETE FROM product_variants WHERE product_id = :pid"),
                    {"pid": product_id},
                )
            else:  # simple → variable
                # Create a default variant from current simple product data
                await db.execute(
                    INSERT_VARIANT_PRODUCT_QUERY,
                    {
                        "product_id": product_id,
                        "sku": data.sku or current["sku"] or f"DEF-{product_id[:8]}",
                        "price": data.base_price
                        or current["base_price"]
                        or Decimal("0.00"),
                        "stock_quantity": data.stock_quantity
                        or current["stock_quantity"]
                        or 0,
                        "re_order_level": data.re_order_level
                        or current["re_order_level"]
                        or 0,
                        "attributes": normalize_attributes({}),
                        "main_image_url": str(data.main_image_url)
                        if data.main_image_url
                        else current.get("main_image_url"),
                        "image_urls": normalize_image_urls(data.image_urls)
                        if data.image_urls
                        else current.get("image_urls", []),
                    },
                )
                # Clear simple-only fields (now stored in variants)
                data.sku = None
                data.base_price = None
                data.stock_quantity = None
                data.re_order_level = None

        # ── Build product update query dynamically ──
        updates: List[str] = []
        params: Dict[str, Any] = {"id": product_id, "tenant_id": tenant_id}

        # Handle image URLs explicitly
        if data.main_image_url is not None:
            updates.append("main_image_url = :main_image_url")
            params["main_image_url"] = (
                str(data.main_image_url) if data.main_image_url else None
            )

        if data.image_urls is not None:
            updates.append("image_urls = :image_urls")
            params["image_urls"] = normalize_image_urls(data.image_urls)

        # Handle other fields
        for field in [
            "name",
            "description",
            "type",
            "base_price",
            "sku",
            "stock_quantity",
            "re_order_level",
        ]:
            value = getattr(data, field, None)
            if value is not None:
                updates.append(f"{field} = :{field}")
                params[field] = value

        # Execute product update if any fields changed
        updated_product = current.copy()

        if updates:
            query = text(f"""
                    UPDATE products
                    SET {", ".join(updates)}, updated_at = NOW()
                    WHERE id = :id AND tenant_id = :tenant_id
                    RETURNING *
                """)
            result = await db.execute(query, params)
            row = result.mappings().first()
            if row:
                updated_product = dict(row)

        # ── Variant operations (only if currently variable) ──
        if not is_now_simple:
            # Track updated variant attributes to prevent duplicates between add/update operations
            # This uses a set of normalized JSON strings for O(1) conflict detection
            updated_variant_attrs = set()

            # Step 1: Update existing variants
            if data.variants_to_update:
                for update_item in data.variants_to_update:
                    vid = str(update_item["id"])
                    var_updates: List[str] = []
                    var_params: Dict[str, Union[str, int, float, dict, list, None]] = {
                        "vid": vid,
                        "pid": product_id,
                    }

                    for key, value in update_item.items():
                        if key == "id" or value is None:
                            continue

                        var_updates.append(f"{key} = :{key}")

                        # Handle image URLs
                        if key == "main_image_url":
                            var_params["main_image_url"] = str(value) if value else None
                        elif key == "image_urls" and type(value) is list:
                            var_params["image_urls"] = normalize_image_urls(value)
                        # Special handling for attributes (needs normalization for uniqueness)
                        elif key == "attributes" and isinstance(value, dict):
                            normalized = normalize_attributes(value)
                            var_params[key] = normalized
                            # Track this attribute combination to prevent duplicates
                            updated_variant_attrs.add(normalized)
                        elif isinstance(value, Decimal):
                            var_params[key] = float(value)
                        elif isinstance(value, dict):
                            var_params[key] = json.dumps(value)
                        elif isinstance(value, (str, int, float, bool)):
                            var_params[key] = value
                        else:
                            var_params[key] = str(value)

                    if var_updates:
                        query = text(f"""
                            UPDATE product_variants
                            SET {", ".join(var_updates)}, updated_at = NOW()
                            WHERE id = :vid AND product_id = :pid
                        """)
                        await db.execute(query, var_params)

            # Step 2: Add new variants (with duplicate detection)
            for v in data.variants_to_add or []:
                normalized_attrs = normalize_attributes(v.attributes)

                # Check if this attribute combination conflicts with updated variants
                if normalized_attrs in updated_variant_attrs:
                    raise ValueError(
                        f"Cannot add variant: attribute combination {v.attributes} "
                        "conflicts with an existing or updated variant"
                    )

                await db.execute(
                    INSERT_VARIANT_PRODUCT_QUERY,
                    {
                        "product_id": product_id,
                        "sku": v.sku,
                        "price": v.price,
                        "stock_quantity": v.stock_quantity,
                        "re_order_level": v.re_order_level,
                        "attributes": normalized_attrs,
                        "main_image_url": str(v.main_image_url)
                        if v.main_image_url
                        else None,
                        "image_urls": normalize_image_urls(v.image_urls),
                    },
                )

            # Step 3: Remove variants (do this last to avoid conflicts during update)
            for vid in data.variants_to_remove or []:
                await db.execute(
                    text(
                        "DELETE FROM product_variants WHERE id = :vid AND product_id = :pid"
                    ),
                    {"vid": str(vid), "pid": product_id},
                )

        # ── Reload variants for response ──
        variants_result = await db.execute(
            GET_VARIANT_PRODUCT_QUERY, {"product_id": product_id}
        )
        updated_product["variants"] = [dict(r) for r in variants_result.mappings()]

        # Return None if no changes were made
        return (
            updated_product
            if any(
                [
                    updates,
                    data.variants_to_add,
                    data.variants_to_remove,
                    data.variants_to_update,
                ]
            )
            else None
        )

    except IntegrityError as e:
        # Handle unique constraint violations
        if any(
            k in str(e)
            for k in [
                "products_sku_key",
                "product_variants_sku_key",
                "product_variants_attributes_key",
                "product_variants_product_id_sku_key",
            ]
        ):
            raise ValueError("SKU or attribute combination already exists")
        raise
    except Exception as e:
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
