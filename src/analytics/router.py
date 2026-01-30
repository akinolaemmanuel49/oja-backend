from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.service import (
    get_dashboard_data_service,
)
from src.core.dependencies import get_current_user, get_db

analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])


@analytics_router.get("/dashboard")
async def get_dashboard_data(
    db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    tenant_id = current_user["tenant_id"]

    dashboard_data = await get_dashboard_data_service(db, tenant_id)

    return dashboard_data
