import unittest
from compilermate.lexer import Lexer
from compilermate.tokens import TokenType
from compilermate.parser import Parser

class TestParser(unittest.TestCase):
    def test_valid_declaration(self):
        source = "int x = 10;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNotNone(ast)
        self.assertEqual(ast.var_type, "int")
        self.assertEqual(ast.name, "x")
        self.assertEqual(ast.value, 10)
        self.assertIsNone(parser.diagnostic)

    def test_missing_semicolon(self):
        source = "int x = 10"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNone(ast)
        diag = parser.diagnostic
        self.assertIsNotNone(diag)
        self.assertEqual(diag.type, "MISSING_TOKEN")
        self.assertEqual(diag.expected, ";")
        self.assertEqual(diag.line, 1)
        # column should be after the last character (10)
        self.assertGreater(diag.column, 0)

if __name__ == '__main__':
    unittest.main()
