import unittest
from compilermate.lexer import Lexer
from compilermate.tokens import TokenType

class TestLexer(unittest.TestCase):
    def test_lexer_tokens(self):
        source = "int x = 10;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        types = [t.type for t in tokens]
        # Expected token sequence (including EOF)
        expected = [TokenType.INT, TokenType.IDENTIFIER, TokenType.ASSIGN,
                    TokenType.INT_LITERAL, TokenType.SEMICOLON, TokenType.EOF]
        self.assertEqual(types, expected)
        # Check lexemes
        lexemes = [t.lexeme for t in tokens]
        self.assertEqual(lexemes, ["int", "x", "=", "10", ";", ""])

if __name__ == '__main__':
    unittest.main()
