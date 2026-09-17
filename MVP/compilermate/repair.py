from dataclasses import dataclass

@dataclass
class Repair:
    """Represents a single repair action derived from a diagnostic.
    For the MVP we only need INSERT operations for a missing semicolon.
    """
    description: str
    operation: str  # e.g., "INSERT"
    text: str        # text to insert, e.g., ";"
    line: int        # line number where insertion should occur (1‑based)
    column: int      # column number (character offset) where insertion should occur
