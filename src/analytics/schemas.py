from pydantic import BaseModel


class DashboardSchema(BaseModel):
    TotalActiveStorefrontsCount: int
    TotalGroupsCount: int
    TotalVisibleProductsCount: int
    TotalUsersCount: int
