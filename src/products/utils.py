"""
Utility functions for product data normalization.

Key functions:
- normalize_attributes: Ensures consistent JSONB attribute ordering for uniqueness constraints
- normalize_image_urls: Validates and converts image URLs to string list
"""

import json
from typing import Dict, List, Optional, Union

from pydantic import HttpUrl


def normalize_attributes(attrs: Dict[str, str]) -> str:
    """
    Normalize attributes dict to a consistent JSON string representation.

    This is critical because PostgreSQL JSONB doesn't guarantee key order,
    but our unique constraint on product_variants.attributes requires
    deterministic serialization.

    Without sorting: {"color": "red", "size": "M"} might not equal {"size": "M", "color": "red"}
    With sorting: Both become '{"color":"red","size":"M"}' (alphabetical keys)

    Args:
        attrs: Dictionary of attribute key-value pairs (e.g., {"color": "Red", "size": "M"})

    Returns:
        JSON string with sorted keys (e.g., '{"color":"Red","size":"M"}')

    Example:
        >>> normalize_attributes({"size": "L", "color": "Blue"})
        '{"color":"Blue","size":"L"}'
    """
    if not attrs:
        return "{}"
    # sort_keys=True ensures deterministic ordering for uniqueness checks
    return json.dumps(attrs, sort_keys=True)


def normalize_image_urls(value: Optional[Union[List[HttpUrl], List[str]]]) -> List[str]:
    """
    Normalize image URLs to a consistent list of strings.

    Handles:
    - None → empty list
    - List of HttpUrl (Pydantic) → List of strings
    - List of strings → List of strings (validation pass-through)

    Args:
        value: Optional list of URLs (as HttpUrl objects or strings)

    Returns:
        List of URL strings (empty list if None)

    Raises:
        ValueError: If value is not None and not a list/tuple

    Examples:
        >>> normalize_image_urls(None)
        []
        >>> normalize_image_urls([HttpUrl("https://example.com/image.jpg")])
        ['https://example.com/image.jpg']
        >>> normalize_image_urls(["https://example.com/a.jpg", "https://example.com/b.jpg"])
        ['https://example.com/a.jpg', 'https://example.com/b.jpg']
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        # Convert each item to string (handles both HttpUrl and str)
        return [str(v) for v in value]
    raise ValueError("image_urls must be a list of URLs")
