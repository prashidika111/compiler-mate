from dataclasses import dataclass
from typing import Optional

@dataclass
class Diagnostic:
    """Structured diagnostic produced by the parser.
    Fields correspond to the specification for Review 1.
    """
    phase: str            # e.g., "syntax"
    type: str             # e.g., "MISSING_TOKEN"
    line: int
    column: int
    expected: str
    actual: str
    message: str
    # possible actions can be derived from type; not required here
