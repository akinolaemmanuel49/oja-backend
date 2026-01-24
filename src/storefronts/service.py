"""
Storefront management service layer.
Handles creation, listing and management of customer-facing storefronts:
- Unique slug enforcement
- Soft-delete via status field
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.storefronts.schemas import StorefrontCreate, StorefrontUpdate


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
    query = text("""
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

    try:
        result = await db.execute(
            query,
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
) -> Optional[Dict[str, Any]]:
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
        text("""
        SELECT id, tenant_id, name, slug, domain, status, created_at, updated_at
        FROM storefronts
        WHERE id = :id AND tenant_id = :tenant_id
    """),
        {"id": storefront_id, "tenant_id": tenant_id},
    )

    row = result.mappings().first()
    return dict(row) if row else None


async def list_storefronts_service(
    db: AsyncSession, tenant_id: str, limit: int = 20, offset: int = 0
) -> List[Dict[str, Any]]:
    """
    List all storefronts belonging to a tenant.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        limit: Pagination limit
        offset: Pagination offset

    Returns:
        List of storefront dictionaries
    """
    result = await db.execute(
        text("""
        SELECT id, tenant_id, name, slug, domain, status, created_at, updated_at
        FROM storefronts
        WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """),
        {"tenant_id": tenant_id, "limit": limit, "offset": offset},
    )

    return [dict(row) for row in result.mappings()]


async def update_storefront_service(
    db: AsyncSession, storefront_id: str, tenant_id: str, data: StorefrontUpdate
) -> Optional[Dict[str, Any]]:
    """
    Partially update storefront properties.

    Args:
        db: Database session
        storefront_id: Storefront UUID
        tenant_id: Tenant scope
        data: Fields to update

    Returns:
        Updated storefront or None if no changes/not found

    Raises:
        ValueError: If slug or name conflict occurs
    """
    try:
        if not any([data.name, data.slug, data.domain, data.status]):
            return None

        updates = []
        params = {"id": storefront_id, "tenant_id": tenant_id}

        if data.name is not None:
            updates.append("name = :name")
            params["name"] = data.name
        if data.slug is not None:
            updates.append("slug = :slug")
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
            RETURNING id, tenant_id, name, slug, domain, status, created_at, updated_at
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
        text("""
        UPDATE storefronts
        SET status = 'deleted', updated_at = NOW()
        WHERE id = :id AND tenant_id = :tenant_id
        RETURNING id
    """),
        {"id": storefront_id, "tenant_id": tenant_id},
    )

    row = result.scalar_one_or_none()
    return row is not None
