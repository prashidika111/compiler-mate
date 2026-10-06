import unittest
from compilermate.lexer import Lexer
from compilermate.tokens import TokenType

class TestLexer(unittest.TestCase):
    def test_lexer_tokens(self):
        source = "int x = 10;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        types = [t.type for t in tokens]
        expected = [TokenType.INT, TokenType.IDENTIFIER, TokenType.ASSIGN,
                    TokenType.INT_LITERAL, TokenType.SEMICOLON, TokenType.EOF]
        self.assertEqual(types, expected)
        lexemes = [t.lexeme for t in tokens]
        self.assertEqual(lexemes, ["int", "x", "=", "10", ";", ""])

    def test_bool_and_boolean_literals(self):
        source = "bool flag = true; bool other = false;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        types = [t.type for t in tokens]
        expected = [
            TokenType.BOOL, TokenType.IDENTIFIER, TokenType.ASSIGN, TokenType.TRUE, TokenType.SEMICOLON,
            TokenType.BOOL, TokenType.IDENTIFIER, TokenType.ASSIGN, TokenType.FALSE, TokenType.SEMICOLON,
            TokenType.EOF
        ]
        self.assertEqual(types, expected)

    def test_multiline_line_column_tracking(self):
        source = "int x = 5;\nbool flag = true;\nx = 10;"
        lexer = Lexer(source)
        tokens = lexer.lex()

        # Token 0: int at line 1, col 1
        self.assertEqual(tokens[0].lexeme, "int")
        self.assertEqual(tokens[0].line, 1)
        self.assertEqual(tokens[0].column, 1)

        # Token 1: x at line 1, col 5
        self.assertEqual(tokens[1].lexeme, "x")
        self.assertEqual(tokens[1].line, 1)
        self.assertEqual(tokens[1].column, 5)

        # Token 5: bool at line 2, col 1
        self.assertEqual(tokens[5].lexeme, "bool")
        self.assertEqual(tokens[5].line, 2)
        self.assertEqual(tokens[5].column, 1)

        # Token 6: flag at line 2, col 6
        self.assertEqual(tokens[6].lexeme, "flag")
        self.assertEqual(tokens[6].line, 2)
        self.assertEqual(tokens[6].column, 6)

        # Token 10: x at line 3, col 1
        self.assertEqual(tokens[10].lexeme, "x")
        self.assertEqual(tokens[10].line, 3)
        self.assertEqual(tokens[10].column, 1)

    def test_unknown_character_single_line(self):
        source = "int x @ 5;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        self.assertIsNotNone(lexer.diagnostic)
        self.assertEqual(lexer.diagnostic.phase, "lexical")
        self.assertEqual(lexer.diagnostic.type, "INVALID_CHARACTER")
        self.assertEqual(lexer.diagnostic.line, 1)
        self.assertEqual(lexer.diagnostic.column, 7)
        self.assertEqual(lexer.diagnostic.actual, "@")
        # Ensure only valid preceding tokens were collected
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].lexeme, "int")
        self.assertEqual(tokens[1].lexeme, "x")

    def test_unknown_character_multiline(self):
        source = "int x = 5;\nbool flag # true;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        self.assertIsNotNone(lexer.diagnostic)
        self.assertEqual(lexer.diagnostic.phase, "lexical")
        self.assertEqual(lexer.diagnostic.type, "INVALID_CHARACTER")
        self.assertEqual(lexer.diagnostic.line, 2)
        self.assertEqual(lexer.diagnostic.column, 11)
        self.assertEqual(lexer.diagnostic.actual, "#")

if __name__ == '__main__':
    unittest.main()
