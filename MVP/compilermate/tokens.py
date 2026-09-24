from enum import Enum, auto
from dataclasses import dataclass

class TokenType(Enum):
    # Keywords
    INT = auto()
    BOOL = auto()
    TRUE = auto()
    FALSE = auto()
    
    # Identifiers & Literals
    IDENTIFIER = auto()
    INT_LITERAL = auto()
    
    # Punctuation & Operators
    ASSIGN = auto()
    SEMICOLON = auto()
    
    # End of file
    EOF = auto()

@dataclass
class Token:
    type: TokenType
    lexeme: str
    line: int
    column: int
