from enum import Enum, auto
from dataclasses import dataclass

class TokenType(Enum):
    INT = auto()
    IDENTIFIER = auto()
    ASSIGN = auto()
    INT_LITERAL = auto()
    SEMICOLON = auto()
    EOF = auto()

@dataclass
class Token:
    type: TokenType
    lexeme: str
    line: int
    column: int
