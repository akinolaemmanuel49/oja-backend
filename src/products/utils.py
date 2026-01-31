import json
from typing import Dict


def normalize_attributes(attrs: Dict[str, str]) -> str:
    """
    Normalize attributes dict to a consistent JSON string representation.
    Sorts keys to ensure {"color": "red", "size": "M"} equals {"size": "M", "color": "red"}

    This is critical because PostgreSQL JSONB doesn't guarantee key order,
    but our unique constraint treats them as different if the serialization differs.
    """
    if not attrs:
        return "{}"
    # Sort by keys to ensure consistent ordering
    return json.dumps(attrs, sort_keys=True)
