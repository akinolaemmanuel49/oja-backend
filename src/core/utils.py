import random
import string
from typing import Optional

# Character set constants (explicit, composable)
LOWERCASE = string.ascii_lowercase
UPPERCASE = string.ascii_uppercase
LETTERS = string.ascii_letters
DIGITS = string.digits
HEX_DIGITS = string.hexdigits.lower()
ALPHANUMERIC = LETTERS + DIGITS
ALPHANUMERIC_LOWER = LOWERCASE + DIGITS
SYMBOLS = string.punctuation


def generate_random_string(
    length: int = 8,
    chars: str = ALPHANUMERIC_LOWER,
    pattern: Optional[str] = None,
) -> str:
    """
    Generate a random string with customizable length, characters, and pattern.

    - If `pattern` is provided (e.g. "XXX-XXX-XXX"), replace 'X' with random chars.
    - If no pattern is provided, generate a random string of the given length.
    """
    if pattern is not None:
        return "".join(random.choice(chars) if c == "X" else c for c in pattern)

    return "".join(random.choice(chars) for _ in range(length))
