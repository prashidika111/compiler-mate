import unittest
from compilermate.lexer import Lexer
from compilermate.parser import Parser
from compilermate.ast import ProgramAST, DeclarationAST, AssignmentAST

class TestParser(unittest.TestCase):
    def test_valid_declaration(self):
        source = "int x = 10;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNotNone(ast)
        self.assertIsInstance(ast, ProgramAST)
        self.assertEqual(len(ast.statements), 1)
        decl = ast.statements[0]
        self.assertIsInstance(decl, DeclarationAST)
        self.assertEqual(decl.var_type, "int")
        self.assertEqual(decl.name, "x")
        self.assertEqual(decl.value, 10)
        self.assertEqual(decl.value_type, "int")
        self.assertIsNone(parser.diagnostic)

    def test_valid_boolean_declaration(self):
        source = "bool flag = true;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNotNone(ast)
        decl = ast.statements[0]
        self.assertEqual(decl.var_type, "bool")
        self.assertEqual(decl.name, "flag")
        self.assertEqual(decl.value, True)
        self.assertEqual(decl.value_type, "bool")

    def test_multiple_statements_ast(self):
        source = "int x = 5;\nbool flag = true;\nx = 10;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNotNone(ast)
        self.assertEqual(len(ast.statements), 3)

        self.assertIsInstance(ast.statements[0], DeclarationAST)
        self.assertEqual(ast.statements[0].name, "x")
        self.assertEqual(ast.statements[0].value, 5)

        self.assertIsInstance(ast.statements[1], DeclarationAST)
        self.assertEqual(ast.statements[1].name, "flag")
        self.assertEqual(ast.statements[1].value, True)

        self.assertIsInstance(ast.statements[2], AssignmentAST)
        self.assertEqual(ast.statements[2].name, "x")
        self.assertEqual(ast.statements[2].value, 10)
        self.assertEqual(ast.statements[2].value_type, "int")
        self.assertFalse(ast.statements[2].is_identifier)

    def test_assignment_with_identifier_rhs(self):
        source = "int x = 1;\nint y = 2;\ny = x;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNotNone(ast)
        assign = ast.statements[2]
        self.assertIsInstance(assign, AssignmentAST)
        self.assertEqual(assign.name, "y")
        self.assertEqual(assign.value, "x")
        self.assertTrue(assign.is_identifier)

    def test_missing_semicolon(self):
        source = "int x = 10"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNone(ast)
        diag = parser.diagnostic
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "syntax")
        self.assertEqual(diag.type, "MISSING_TOKEN")
        self.assertEqual(diag.expected, ";")
        self.assertEqual(diag.line, 1)
        self.assertGreater(diag.column, 0)

    def test_empty_program(self):
        source = ""
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNone(ast)
        self.assertIsNotNone(parser.diagnostic)
        self.assertEqual(parser.diagnostic.type, "MISSING_TOKEN")

    def test_unexpected_token_statement_start(self):
        source = "= 10;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNone(ast)
        diag = parser.diagnostic
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "syntax")
        self.assertEqual(diag.type, "UNEXPECTED_TOKEN")
        self.assertEqual(diag.actual, "=")

    def test_unexpected_token_after_type(self):
        source = "int = 10;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNone(ast)
        diag = parser.diagnostic
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "syntax")
        self.assertEqual(diag.type, "UNEXPECTED_TOKEN")
        self.assertEqual(diag.actual, "=")

    def test_unexpected_token_in_declaration_literal(self):
        source = "int x = int;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNone(ast)
        diag = parser.diagnostic
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "syntax")
        self.assertEqual(diag.type, "UNEXPECTED_TOKEN")
        self.assertEqual(diag.actual, "int")

    def test_unexpected_token_in_assignment_rvalue(self):
        source = "x = =;"
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertIsNone(ast)
        diag = parser.diagnostic
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "syntax")
        self.assertEqual(diag.type, "UNEXPECTED_TOKEN")
        self.assertEqual(diag.actual, "=")

if __name__ == '__main__':
    unittest.main()
