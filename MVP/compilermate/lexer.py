from typing import List, Optional
from .tokens import Token, TokenType
from .diagnostics import Diagnostic

class Lexer:
    """Hand-written lexer for the CompilerMate language.
    Supports: int, bool, true, false, identifiers, integer literals, '=', ';', and EOF.
    Tracks 1-based line and column positions accurately across multiline sources.
    Halts and produces a structured lexical diagnostic upon encountering unrecognized characters.
    """
    KEYWORDS = {
        "int": TokenType.INT,
        "bool": TokenType.BOOL,
        "true": TokenType.TRUE,
        "false": TokenType.FALSE,
    }

    def __init__(self, source: str):
        self.source = source
        self.current = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
        self.diagnostic: Optional[Diagnostic] = None

    def lex(self) -> List[Token]:
        while not self._is_at_end():
            self._skip_whitespace()
            if self._is_at_end():
                break
            start_line = self.line
            start_col = self.column
            ch = self._peek()

            if ch.isalpha() or ch == '_':
                lexeme = self._identifier()
                token_type = self.KEYWORDS.get(lexeme, TokenType.IDENTIFIER)
                self._add_token(token_type, lexeme, start_line, start_col)
            elif ch.isdigit():
                lexeme = self._number()
                self._add_token(TokenType.INT_LITERAL, lexeme, start_line, start_col)
            elif ch == '=':
                self._advance()
                self._add_token(TokenType.ASSIGN, '=', start_line, start_col)
            elif ch == ';':
                self._advance()
                self._add_token(TokenType.SEMICOLON, ';', start_line, start_col)
            else:
                bad_char = self._advance()
                self.diagnostic = Diagnostic(
                    phase="lexical",
                    type="INVALID_CHARACTER",
                    line=start_line,
                    column=start_col,
                    expected="valid token",
                    actual=bad_char,
                    message=f"Unrecognized character '{bad_char}'"
                )
                return self.tokens

        # EOF token at final position
        self._add_token(TokenType.EOF, '', self.line, self.column)
        return self.tokens

    def _is_at_end(self) -> bool:
        return self.current >= len(self.source)

    def _peek(self) -> str:
        return self.source[self.current]

    def _advance(self) -> str:
        ch = self.source[self.current]
        self.current += 1
        if ch == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _add_token(self, type_: TokenType, lexeme: str, line: int, column: int) -> None:
        self.tokens.append(Token(type_, lexeme, line, column))

    def _skip_whitespace(self) -> None:
        while not self._is_at_end() and self._peek().isspace():
            self._advance()

    def _identifier(self) -> str:
        start = self.current
        while not self._is_at_end() and (self._peek().isalnum() or self._peek() == '_'):
            self._advance()
        return self.source[start:self.current]

    def _number(self) -> str:
        start = self.current
        while not self._is_at_end() and self._peek().isdigit():
            self._advance()
        return self.source[start:self.current]
