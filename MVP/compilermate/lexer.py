from .tokens import Token, TokenType
class Lexer:
    """Simple hand‑written lexer for the minimal language.
    Recognises the tokens needed for a single declaration.
    """
    KEYWORDS = {"int": TokenType.INT}
    def __init__(self, source: str):
        self.source = source
        self.current = 0
        self.line = 1
        self.column = 1
        self.tokens = []
    def lex(self):
        while not self._is_at_end():
            self._skip_whitespace()
            if self._is_at_end():
                break
            start_col = self.column
            ch = self._peek()
            if ch.isalpha():
                lexeme = self._identifier()
                token_type = self.KEYWORDS.get(lexeme, TokenType.IDENTIFIER)
                self._add_token(token_type, lexeme, self.line, start_col)
            elif ch.isdigit():
                lexeme = self._number()
                self._add_token(TokenType.INT_LITERAL, lexeme, self.line, start_col)
            elif ch == '=':
                self._advance()
                self._add_token(TokenType.ASSIGN, '=', self.line, start_col)
            elif ch == ';':
                self._advance()
                self._add_token(TokenType.SEMICOLON, ';', self.line, start_col)
            else:
                # Unknown character – skip it (the parser will later error)
                self._advance()
        # EOF token
        self._add_token(TokenType.EOF, '', self.line, self.column)
        return self.tokens
    # ----- helpers -----
    def _is_at_end(self):
        return self.current >= len(self.source)
    def _peek(self):
        return self.source[self.current]
    def _advance(self):
        ch = self.source[self.current]
        self.current += 1
        self.column += 1
        return ch
    def _add_token(self, type_, lexeme, line, column):
        self.tokens.append(Token(type_, lexeme, line, column))
    def _skip_whitespace(self):
        while not self._is_at_end() and self._peek().isspace():
            self._advance()
    def _identifier(self):
        start = self.current
        while not self._is_at_end() and (self._peek().isalnum() or self._peek() == '_'):
            self._advance()
        return self.source[start:self.current]
    def _number(self):
        start = self.current
        while not self._is_at_end() and self._peek().isdigit():
            self._advance()
        return self.source[start:self.current]
