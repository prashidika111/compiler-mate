from dataclasses import dataclass
from typing import Optional

@dataclass
class Diagnostic:
    """Structured diagnostic produced by the compiler (syntax or semantic).
    Fields:
    - phase: "syntax" | "semantic"
    - type: diagnostic error code (e.g., "MISSING_TOKEN", "REDECLARATION", "UNDECLARED_IDENTIFIER", "TYPE_MISMATCH_DECL", "TYPE_MISMATCH_ASSIGN")
    - line: 1-based source line
    - column: 1-based source column
    - expected: description of what was expected
    - actual: description of what was actually encountered
    - message: human-readable error description
    - symbol: optional identifier name involved in the diagnostic
    """
    phase: str
    type: str
    line: int
    column: int
    expected: str
    actual: str
    message: str
    symbol: Optional[str] = None
