from typing import List

from pydantic import BaseModel


class PaginatedResponse[T](BaseModel):
    data: List[T]
    total: int
    page: int
    page_size: int
