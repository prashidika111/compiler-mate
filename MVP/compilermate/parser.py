from typing import List, Optional, Union
from .tokens import Token, TokenType
from .diagnostics import Diagnostic
from .ast import ProgramAST, DeclarationAST, AssignmentAST

class Parser:
    """Recursive-descent parser for the CompilerMate grammar:
    program      → statement+ EOF
    statement    → declaration | assignment
    declaration  → ("int" | "bool") IDENTIFIER "=" literal ";"
    assignment   → IDENTIFIER "=" rvalue ";"
    rvalue       → literal | IDENTIFIER
    literal      → INT_LITERAL | "true" | "false"
    """

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.current = 0
        self.diagnostic: Optional[Diagnostic] = None

    def parse(self) -> Optional[ProgramAST]:
        statements = []

        if self._is_at_end():
            tok = self._peek()
            self.diagnostic = Diagnostic(
                phase="syntax",
                type="MISSING_TOKEN",
                line=tok.line,
                column=tok.column,
                expected="statement",
                actual="EOF",
                message="Expected at least one statement"
            )
            return None

        while not self._is_at_end():
            stmt = self._parse_statement()
            if stmt is None:
                return None
            statements.append(stmt)

        # Validate EOF / trailing tokens
        if not self._is_at_end():
            tok = self._peek()
            self.diagnostic = Diagnostic(
                phase="syntax",
                type="UNEXPECTED_TOKEN",
                line=tok.line,
                column=tok.column,
                expected="EOF",
                actual=tok.lexeme if tok.type != TokenType.EOF else "EOF",
                message=f"Unexpected token '{tok.lexeme}' after program"
            )
            return None

        return ProgramAST(statements=statements)

    def _parse_statement(self) -> Optional[Union[DeclarationAST, AssignmentAST]]:
        if self._check(TokenType.INT) or self._check(TokenType.BOOL):
            return self._parse_declaration()
        elif self._check(TokenType.IDENTIFIER):
            return self._parse_assignment()
        else:
            tok = self._peek()
            is_eof = tok.type == TokenType.EOF
            self.diagnostic = Diagnostic(
                phase="syntax",
                type="MISSING_TOKEN" if is_eof else "UNEXPECTED_TOKEN",
                line=tok.line,
                column=tok.column,
                expected="declaration or assignment",
                actual=tok.lexeme if not is_eof else "EOF",
                message=f"Expected declaration or assignment, got '{tok.lexeme if not is_eof else 'EOF'}'"
            )
            return None

    def _parse_declaration(self) -> Optional[DeclarationAST]:
        type_tok = self._advance()
        ident_tok = self._consume(TokenType.IDENTIFIER, "identifier")
        if ident_tok is None:
            return None

        assign_tok = self._consume(TokenType.ASSIGN, "'='")
        if assign_tok is None:
            return None

        # Parse literal
        if self._check(TokenType.INT_LITERAL):
            lit_tok = self._advance()
            val = int(lit_tok.lexeme)
            val_type = "int"
        elif self._check(TokenType.TRUE):
            lit_tok = self._advance()
            val = True
            val_type = "bool"
        elif self._check(TokenType.FALSE):
            lit_tok = self._advance()
            val = False
            val_type = "bool"
        else:
            tok = self._peek()
            is_eof = tok.type == TokenType.EOF
            self.diagnostic = Diagnostic(
                phase="syntax",
                type="MISSING_TOKEN" if is_eof else "UNEXPECTED_TOKEN",
                line=tok.line,
                column=tok.column,
                expected="literal",
                actual=tok.lexeme if not is_eof else "EOF",
                message="Expected literal ('int' literal, 'true', or 'false')"
            )
            return None

        # Expect semicolon
        if self._match(TokenType.SEMICOLON):
            return DeclarationAST(
                var_type=type_tok.lexeme,
                name=ident_tok.lexeme,
                value=val,
                value_type=val_type,
                line=type_tok.line,
                column=type_tok.column
            )
        else:
            next_tok = self._peek()
            self.diagnostic = Diagnostic(
                phase="syntax",
                type="MISSING_TOKEN",
                line=next_tok.line,
                column=next_tok.column,
                expected=";",
                actual=next_tok.lexeme if next_tok.type != TokenType.EOF else "EOF",
                message="Expected ';' after expression"
            )
            return None

    def _parse_assignment(self) -> Optional[AssignmentAST]:
        ident_tok = self._advance()
        assign_tok = self._consume(TokenType.ASSIGN, "'='")
        if assign_tok is None:
            return None

        # Parse rvalue -> literal | IDENTIFIER
        if self._check(TokenType.INT_LITERAL):
            lit_tok = self._advance()
            val = int(lit_tok.lexeme)
            val_type = "int"
            is_ident = False
            rv_line = lit_tok.line
            rv_col = lit_tok.column
        elif self._check(TokenType.TRUE):
            lit_tok = self._advance()
            val = True
            val_type = "bool"
            is_ident = False
            rv_line = lit_tok.line
            rv_col = lit_tok.column
        elif self._check(TokenType.FALSE):
            lit_tok = self._advance()
            val = False
            val_type = "bool"
            is_ident = False
            rv_line = lit_tok.line
            rv_col = lit_tok.column
        elif self._check(TokenType.IDENTIFIER):
            var_tok = self._advance()
            val = var_tok.lexeme
            val_type = "identifier"
            is_ident = True
            rv_line = var_tok.line
            rv_col = var_tok.column
        else:
            tok = self._peek()
            is_eof = tok.type == TokenType.EOF
            self.diagnostic = Diagnostic(
                phase="syntax",
                type="MISSING_TOKEN" if is_eof else "UNEXPECTED_TOKEN",
                line=tok.line,
                column=tok.column,
                expected="rvalue",
                actual=tok.lexeme if not is_eof else "EOF",
                message="Expected literal or identifier"
            )
            return None

        if self._match(TokenType.SEMICOLON):
            return AssignmentAST(
                name=ident_tok.lexeme,
                value=val,
                value_type=val_type,
                is_identifier=is_ident,
                rvalue_line=rv_line,
                rvalue_column=rv_col,
                line=ident_tok.line,
                column=ident_tok.column
            )
        else:
            next_tok = self._peek()
            self.diagnostic = Diagnostic(
                phase="syntax",
                type="MISSING_TOKEN",
                line=next_tok.line,
                column=next_tok.column,
                expected=";",
                actual=next_tok.lexeme if next_tok.type != TokenType.EOF else "EOF",
                message="Expected ';' after expression"
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
        tok = self._peek()
        is_eof = tok.type == TokenType.EOF
        self.diagnostic = Diagnostic(
            phase="syntax",
            type="MISSING_TOKEN" if is_eof else "UNEXPECTED_TOKEN",
            line=tok.line,
            column=tok.column,
            expected=token_type.name,
            actual=tok.lexeme if not is_eof else "EOF",
            message=f"Expected {description}"
        )
        return None
