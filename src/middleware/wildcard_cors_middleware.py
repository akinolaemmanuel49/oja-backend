import re

from fastapi.middleware.cors import CORSMiddleware


def parse_origin_patterns(patterns):
    """Convert wildcard patterns to regex patterns"""
    compiled_patterns = []
    for pattern in patterns:
        # Escape regex special characters except *
        pattern = re.escape(pattern).replace("\\*", ".*")
        # Make sure it matches the entire string
        pattern = f"^{pattern}$"
        compiled_patterns.append(re.compile(pattern))
    return compiled_patterns


class WildcardCORSMiddleware(CORSMiddleware):
    def __init__(self, app, *args, **kwargs):
        super().__init__(app, *args, **kwargs)
        # Compile the origin patterns
        if hasattr(self, "allow_origins"):
            self.origin_patterns = parse_origin_patterns(self.allow_origins)
        else:
            self.origin_patterns = []

    def is_allowed_origin(self, origin: str) -> bool:
        # First check exact matches
        if super().is_allowed_origin(origin):
            return True

        # Then check pattern matches
        for pattern in self.origin_patterns:
            if pattern.match(origin):
                return True
        return False
