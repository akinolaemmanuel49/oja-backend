from typing import List, Literal, Union

from pydantic import BaseModel


class PermissionsRequest(BaseModel):
    target_type: Union[
        Literal["user"], Literal["group"], Literal["role"]
    ]  # "user", "group", "role"
    target_id: str  # UUID as string
    permission_codes: List[str]


class PermissionRequest(BaseModel):
    target_type: Union[
        Literal["user"], Literal["group"], Literal["role"]
    ]  # "user", "group", "role"
    target_id: str  # UUID as string
    permission_code: str
