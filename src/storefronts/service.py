"""
Storefront management service layer.
Handles creation, listing and management of customer-facing storefronts:
- Unique slug enforcement
- Soft-delete via status field
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.responses import PaginatedResponse
from src.storefronts.schemas import StorefrontCreate, StorefrontOut, StorefrontUpdate

INSERT_STOREFRONT_QUERY = text("""
    INSERT INTO storefronts (
        tenant_id, name, slug, domain, status,
        created_at, updated_at
    )
    VALUES (
        :tenant_id, :name, :slug, :domain, :status,
        NOW(), NOW()
    )
    RETURNING id, tenant_id, name, slug, domain, status, created_at, updated_at
""")

GET_STOREFRONT_QUERY = text("""
    SELECT id, tenant_id, name, slug, slug_updated_at, domain, status, design_config, deleted_at, created_at, updated_at
    FROM storefronts
    WHERE id = :id AND tenant_id = :tenant_id
""")

GET_STOREFRONT_BY_SLUG_QUERY = text("""
    SELECT id, tenant_id, name, slug, slug_updated_at, domain, status, design_config, deleted_at, created_at, updated_at
    FROM storefronts
    WHERE slug = :slug
""")

LIST_STOREFRONTS_QUERY = text("""
SELECT id, tenant_id, name, slug, slug_updated_at, domain, status, design_config, deleted_at, created_at, updated_at
FROM storefronts
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC
LIMIT :limit OFFSET :offset
""")

COUNT_STOREFRONTS_QUERY = text("""
    SELECT COUNT(*)
    FROM storefronts
    WHERE tenant_id = :tenant_id
""")

UPDATE_STOREFRONT_QUERY = text("""
UPDATE storefronts
SET status = 'deleted', updated_at = NOW(), deleted_at = NOW()
WHERE id = :id AND tenant_id = :tenant_id
RETURNING id
""")

SAVE_DESIGN_CONFIG_QUERY = text("""
    UPDATE storefronts
    SET design_config = :design_config, updated_at = NOW()
    WHERE id = :storefront_id AND tenant_id = :tenant_id
    RETURNING id
""")

GET_DESIGN_CONFIG_QUERY = text("""
    SELECT design_config
    FROM storefronts
    WHERE id = :storefront_id AND tenant_id = :tenant_id
""")


async def create_storefront_service(
    db: AsyncSession, tenant_id: str, data: StorefrontCreate
) -> Dict[str, Any]:
    """
    Create a new storefront for a tenant.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        data: Storefront creation data

    Returns:
        Created storefront dictionary

    Raises:
        ValueError: If slug or name already taken
    """

    try:
        result = await db.execute(
            INSERT_STOREFRONT_QUERY,
            {
                "tenant_id": tenant_id,
                "name": data.name,
                "slug": data.slug,
                "domain": data.domain,
                "status": data.status,
            },
        )

        row = result.mappings().first()
        if not row:
            raise RuntimeError("Failed to create storefront")

        return dict(row)
    except IntegrityError as e:
        if "storefronts_slug_key" in str(e):
            raise ValueError("Storefront slug already taken")
        elif "storefronts_tenant_id_name_key" in str(e):
            raise ValueError("Storefront name already taken")
        raise ValueError("Database constraint violation") from e
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to create storefront: {str(e)}") from e


async def get_storefront_service(
    db: AsyncSession, storefront_id: str, tenant_id: str
) -> StorefrontOut:
    """
    Retrieve a single storefront by ID (tenant-scoped).

    Args:
        db: Database session
        storefront_id: Storefront UUID
        tenant_id: Tenant scope

    Returns:
        Storefront dictionary or None if not found
    """
    result = await db.execute(
        GET_STOREFRONT_QUERY,
        {"id": storefront_id, "tenant_id": tenant_id},
    )

    row = result.mappings().first()
    if row:
        return StorefrontOut(**dict(row))
    raise ValueError("Storefront not found")


async def get_resolve_slug_and_get_storefront_service(
    db: AsyncSession, storefront_slug: str
) -> StorefrontOut:
    """
    Retrieve a single storefront by slug.

    Args:
        db: Database session
        storefront_slug: Storefront slug

    Returns:
        Storefront dictionary or None if not found
    """
    result = await db.execute(
        GET_STOREFRONT_BY_SLUG_QUERY,
        {"slug": storefront_slug},
    )

    row = result.mappings().first()
    if row:
        return StorefrontOut(**dict(row))
    raise ValueError("Storefront not found")


async def list_storefronts_service(
    db: AsyncSession, tenant_id: str, page: int = 1, page_size: int = 20
) -> PaginatedResponse[StorefrontOut]:
    """
    List all storefronts belonging to a tenant.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Paginated list of groups storefronts
    """
    offset = (page - 1) * page_size

    # Get storefronts
    storefronts_result = await db.execute(
        LIST_STOREFRONTS_QUERY,
        {"tenant_id": tenant_id, "limit": page_size, "offset": offset},
    )

    storefronts_rows = storefronts_result.mappings().all()
    storefronts = [StorefrontOut(**row) for row in storefronts_rows]

    # Get total count
    count_result = await db.execute(
        COUNT_STOREFRONTS_QUERY,
        {"tenant_id": tenant_id},
    )
    total = count_result.scalar_one()

    return PaginatedResponse(
        data=storefronts,
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_storefront_service(
    db: AsyncSession, storefront_id: str, tenant_id: str, data: StorefrontUpdate
) -> Optional[Dict[str, Any]]:
    try:
        if not any([data.name, data.slug, data.domain, data.status]):
            return None

        # Handle Slug Change Restriction Logic
        if data.slug is not None:
            # Fetch current slug and last update time
            check_query = text("""
                SELECT slug, slug_updated_at FROM storefronts
                WHERE id = :id AND tenant_id = :tenant_id
            """)
            current = await db.execute(
                check_query, {"id": storefront_id, "tenant_id": tenant_id}
            )
            row = current.mappings().first()

            if not row:
                return None

            # Only enforce the 30-day rule if the slug is actually changing
            if row["slug"] != data.slug:
                if row["slug_updated_at"] is not None:
                    # Check if 30 days have passed
                    # Note: Using database-agnostic comparison or Python side
                    last_update = row["slug_updated_at"]
                    if datetime.now(timezone.utc) < last_update + timedelta(days=30):
                        days_remaining = (
                            30 - (datetime.now(timezone.utc) - last_update).days
                        )
                        raise ValueError(
                            f"Slug can only be changed once every 30 days. Please wait {days_remaining} more days."
                        )

        updates = []
        params = {"id": storefront_id, "tenant_id": tenant_id}

        if data.name is not None:
            updates.append("name = :name")
            params["name"] = data.name

        if data.slug is not None:
            updates.append("slug = :slug")
            # If the slug is actually different, update the cooldown timer
            updates.append("slug_updated_at = NOW()")
            params["slug"] = data.slug

        if data.domain is not None:
            updates.append("domain = :domain")
            params["domain"] = data.domain

        if data.status is not None:
            updates.append("status = :status")
            params["status"] = data.status

        query = text(f"""
            UPDATE storefronts
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING id, tenant_id, name, slug, domain, status, created_at, updated_at, slug_updated_at
        """)

        result = await db.execute(query, params)
        row = result.mappings().first()
        return dict(row) if row else None

    except IntegrityError as e:
        if "storefronts_slug_key" in str(e):
            raise ValueError("Storefront slug already taken")
        elif "storefronts_tenant_id_name_key" in str(e):
            raise ValueError("Storefront name already taken")
        raise ValueError("Database constraint violation") from e
    except ValueError:
        raise  # Re-raise our cooldown error
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to update storefront: {str(e)}") from e


async def delete_storefront_service(
    db: AsyncSession, storefront_id: str, tenant_id: str
) -> bool:
    """
    Soft-delete a storefront (sets status = 'deleted').

    Args:
        db: Database session
        storefront_id: Storefront UUID
        tenant_id: Tenant scope

    Returns:
        True if storefront was marked deleted, False if not found
    """
    result = await db.execute(
        UPDATE_STOREFRONT_QUERY,
        {"id": storefront_id, "tenant_id": tenant_id},
    )

    row = result.scalar_one_or_none()
    return row is not None


async def save_design_config_service(
    db: AsyncSession, storefront_id: str, tenant_id: str, design_config: Dict[str, Any]
) -> bool:
    """
    Save the design configuration for a storefront.

    Args:
        db: Database session
        storefront_id: Storefront UUID
        tenant_id: Tenant scope (for security)
        design_config: The complete design JSON

    Returns:
        True if saved successfully

    Raises:
        ValueError: If storefront not found
    """
    result = await db.execute(
        SAVE_DESIGN_CONFIG_QUERY,
        {
            "storefront_id": storefront_id,
            "tenant_id": tenant_id,
            "design_config": json.dumps(design_config),
        },
    )

    row = result.scalar_one_or_none()
    if not row:
        raise ValueError("Storefront not found")

    return True


async def get_design_config_service(
    db: AsyncSession, storefront_id: str, tenant_id: str
) -> Optional[Dict[str, Any]]:
    """
    Retrieve the design configuration for a storefront.

    Args:
        db: Database session
        storefront_id: Storefront UUID
        tenant_id: Tenant scope

    Returns:
        Design config dict or None
    """
    result = await db.execute(
        GET_DESIGN_CONFIG_QUERY,
        {"storefront_id": storefront_id, "tenant_id": tenant_id},
    )

    row = result.mappings().first()
    if row:
        return row.get("design_config")
    return None
