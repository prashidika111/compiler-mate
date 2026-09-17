from dataclasses import dataclass
from typing import Optional

@dataclass
class DeclarationAST:
    """AST node for a single variable declaration.
    Only the fields required for the Review 1 slice are stored.
    """
    var_type: str  # e.g., "int"
    name: str      # identifier
    value: int     # integer literal value
