from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.schemas import DashboardSchema

GET_TOTAL_ACTIVE_STOREFRONTS = text("""
    SELECT COUNT(*) FROM storefronts WHERE tenant_id = :tenant_id AND status = 'active';
""")

GET_TOTAL_VISIBLE_PRODUCTS = text("""
    SELECT COUNT(*)
    FROM products
    INNER JOIN storefront_products
        ON products.id = storefront_products.product_id
    WHERE products.tenant_id = :tenant_id
    AND storefront_products.is_visible = true;
""")

GET_TOTAL_PRODUCTS = text("""
    SELECT COUNT(*) FROM products WHERE tenant_id = :tenant_id;
""")

GET_TOTAL_USERS = text("""
    SELECT COUNT(*) FROM users WHERE tenant_id = :tenant_id AND is_active = true AND deleted_at IS NULL;
""")

GET_TOTAL_GROUPS = text("""
    SELECT COUNT(*) FROM groups WHERE tenant_id = :tenant_id;
""")


async def get_total_active_storefronts_service(db: AsyncSession, tenant_id: str):
    result = await db.execute(GET_TOTAL_ACTIVE_STOREFRONTS, {"tenant_id": tenant_id})
    return result.scalar_one()


async def get_total_groups_service(db: AsyncSession, tenant_id: str):
    result = await db.execute(GET_TOTAL_GROUPS, {"tenant_id": tenant_id})
    return result.scalar_one()


# async def get_total_visible_products_service(db: AsyncSession, tenant_id: str):
#     result = await db.execute(GET_TOTAL_VISIBLE_PRODUCTS, {"tenant_id": tenant_id})
#     return result.scalar_one()


async def get_total_products_service(db: AsyncSession, tenant_id: str):
    result = await db.execute(GET_TOTAL_PRODUCTS, {"tenant_id": tenant_id})
    return result.scalar_one()


async def get_total_users_service(db: AsyncSession, tenant_id: str):
    result = await db.execute(GET_TOTAL_USERS, {"tenant_id": tenant_id})
    return result.scalar_one()


async def get_dashboard_data_service(db: AsyncSession, tenant_id: str):
    total_active_storefronts = await get_total_active_storefronts_service(db, tenant_id)
    total_groups = await get_total_groups_service(db, tenant_id)
    total_visible_products = await get_total_products_service(db, tenant_id)
    total_users = await get_total_users_service(db, tenant_id)
    return DashboardSchema(
        TotalActiveStorefrontsCount=total_active_storefronts,
        TotalGroupsCount=total_groups,
        TotalVisibleProductsCount=total_visible_products,
        TotalUsersCount=total_users,
    )
