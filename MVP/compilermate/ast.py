from dataclasses import dataclass, field
from typing import List, Union, Any

@dataclass
class DeclarationAST:
    """AST node for a variable declaration.
    declaration -> ("int" | "bool") IDENTIFIER "=" literal ";"
    """
    var_type: str          # "int" or "bool"
    name: str              # identifier name
    value: Any             # integer value or boolean value (e.g., 10, True, False)
    value_type: str = ""   # "int" or "bool"
    line: int = 1
    column: int = 1

@dataclass
class AssignmentAST:
    """AST node for a variable assignment.
    assignment -> IDENTIFIER "=" rvalue ";"
    rvalue     -> literal | IDENTIFIER
    """
    name: str              # target identifier name
    value: Any             # literal value or identifier name
    value_type: str = ""   # "int", "bool", or "identifier"
    is_identifier: bool = False # True if RHS is an identifier reference
    rvalue_line: int = 1
    rvalue_column: int = 1
    line: int = 1
    column: int = 1

@dataclass
class ProgramAST:
    """AST node for the full program containing multiple statements."""
    statements: List[Union[DeclarationAST, AssignmentAST]] = field(default_factory=list)

    def __iter__(self):
        return iter(self.statements)

    def __len__(self):
        return len(self.statements)

    def __getitem__(self, index):
        return self.statements[index]
