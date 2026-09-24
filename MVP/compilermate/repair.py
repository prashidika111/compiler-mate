from dataclasses import dataclass

@dataclass
class Repair:
    """Represents a single repair action derived from a diagnostic.
    Only deterministic syntax repairs (e.g. missing semicolon) are supported.
    Semantic diagnostics do not produce automated repairs.
    """
    description: str
    operation: str  # e.g., "INSERT"
    text: str        # text to insert, e.g., ";"
    line: int        # line number where insertion should occur (1‑based)
    column: int      # column number (character offset) where insertion should occur
