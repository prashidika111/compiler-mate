from typing import List, Optional
from .tokens import Token, TokenType
from .diagnostics import Diagnostic
from .ast import DeclarationAST

class Parser:
    """Very small recursive‑descent parser for a single declaration.
    On success returns a DeclarationAST. On failure returns a Diagnostic.
    """

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.current = 0
        self.diagnostic: Optional[Diagnostic] = None

    def parse(self) -> Optional[DeclarationAST]:
        # declaration -> type IDENTIFIER "=" INT_LITERAL ";"
        # We will attempt to consume in order, and if the final semicolon is missing, report it.
        type_tok = self._consume(TokenType.INT, "type 'int'")
        if type_tok is None:
            return None
        ident_tok = self._consume(TokenType.IDENTIFIER, "identifier")
        if ident_tok is None:
            return None
        assign_tok = self._consume(TokenType.ASSIGN, "'='")
        if assign_tok is None:
            return None
        lit_tok = self._consume(TokenType.INT_LITERAL, "integer literal")
        if lit_tok is None:
            return None
        # Expect semicolon
        if self._match(TokenType.SEMICOLON):
            # Successful parse, construct AST
            return DeclarationAST(var_type=type_tok.lexeme,
                                   name=ident_tok.lexeme,
                                   value=int(lit_tok.lexeme))
        else:
            # Missing semicolon – create diagnostic using the location where it was expected
            # The next token is either EOF or something else; we use the current token for location
            next_tok = self._peek()
            line = next_tok.line
            column = next_tok.column
            self.diagnostic = Diagnostic(
                phase="syntax",
                type="MISSING_TOKEN",
                line=line,
                column=column,
                expected=";",
                actual=next_tok.lexeme if next_tok.type != TokenType.EOF else "EOF",
                message=f"Expected ';' after expression"
            )
            return None

    # ----- helper methods -----
    def _peek(self) -> Token:
        return self.tokens[self.current]

    def _advance(self) -> Token:
        if not self._is_at_end():
            self.current += 1
        return self.tokens[self.current - 1]

    def _is_at_end(self) -> bool:
        return self._peek().type == TokenType.EOF

    def _match(self, token_type: TokenType) -> bool:
        if self._check(token_type):
            self._advance()
            return True
        return False

    def _check(self, token_type: TokenType) -> bool:
        return not self._is_at_end() and self._peek().type == token_type

    def _consume(self, token_type: TokenType, description: str) -> Optional[Token]:
        if self._check(token_type):
            return self._advance()
        # Missing expected token – create diagnostic (simplified for non‑semicolon cases)
        tok = self._peek()
        self.diagnostic = Diagnostic(
            phase="syntax",
            type="MISSING_TOKEN",
            line=tok.line,
            column=tok.column,
            expected=token_type.name,
            actual=tok.lexeme if tok.type != TokenType.EOF else "EOF",
            message=f"Expected {description}"
        )
        return None
