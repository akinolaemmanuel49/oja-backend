from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.storefronts.schemas import StorefrontCreate, StorefrontUpdate


async def create_storefront(
    db: AsyncSession, tenant_id: str, data: StorefrontCreate
) -> Dict[str, Any]:
    """Create a new storefront for a tenant."""
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


async def get_storefront(
    db: AsyncSession, storefront_id: str, tenant_id: str
) -> Optional[Dict[str, Any]]:
    """Retrieve a single storefront (tenant-scoped)."""
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


async def list_storefronts(
    db: AsyncSession, tenant_id: str, limit: int = 20, offset: int = 0
) -> List[Dict[str, Any]]:
    """List all storefronts for a tenant."""
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


async def update_storefront(
    db: AsyncSession, storefront_id: str, tenant_id: str, data: StorefrontUpdate
) -> Optional[Dict[str, Any]]:
    """Update an existing storefront (tenant-scoped)."""
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


async def delete_storefront(
    db: AsyncSession, storefront_id: str, tenant_id: str
) -> bool:
    """Soft-delete a storefront by setting status='deleted'."""
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
