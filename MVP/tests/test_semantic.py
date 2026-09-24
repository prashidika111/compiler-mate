import unittest
from compilermate.lexer import Lexer
from compilermate.parser import Parser
from compilermate.symbol_table import SymbolTable
from compilermate.semantic import SemanticAnalyzer

class TestSemanticAnalysis(unittest.TestCase):
    def _analyze_source(self, source: str):
        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)
        ast = parser.parse()
        st = SymbolTable()
        analyzer = SemanticAnalyzer(st)
        diag = analyzer.analyze(ast)
        return ast, st, diag

    def test_valid_program(self):
        source = "int x = 5;\nbool flag = true;\nx = 10;"
        ast, st, diag = self._analyze_source(source)
        self.assertIsNone(diag)
        self.assertEqual(len(st), 2)
        self.assertEqual(st.lookup("x").type, "int")
        self.assertEqual(st.lookup("flag").type, "bool")

    def test_redeclaration(self):
        source = "int x = 1;\nint x = 2;"
        ast, st, diag = self._analyze_source(source)
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "semantic")
        self.assertEqual(diag.type, "REDECLARATION")
        self.assertEqual(diag.symbol, "x")
        self.assertEqual(diag.line, 2)
        self.assertEqual(diag.expected, "unique identifier")
        self.assertEqual(diag.actual, "x already declared as int at line 1")

    def test_undeclared_identifier_lhs(self):
        source = "y = 1;"
        ast, st, diag = self._analyze_source(source)
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "semantic")
        self.assertEqual(diag.type, "UNDECLARED_IDENTIFIER")
        self.assertEqual(diag.symbol, "y")
        self.assertEqual(diag.line, 1)

    def test_undeclared_identifier_rhs(self):
        source = "int x = 1;\nx = y;"
        ast, st, diag = self._analyze_source(source)
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "semantic")
        self.assertEqual(diag.type, "UNDECLARED_IDENTIFIER")
        self.assertEqual(diag.symbol, "y")

    def test_type_mismatch_declaration(self):
        source = "bool b = 5;"
        ast, st, diag = self._analyze_source(source)
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "semantic")
        self.assertEqual(diag.type, "TYPE_MISMATCH_DECL")
        self.assertEqual(diag.symbol, "b")
        self.assertEqual(diag.expected, "bool")
        self.assertEqual(diag.actual, "int")

    def test_type_mismatch_declaration_int_with_bool(self):
        source = "int a = true;"
        ast, st, diag = self._analyze_source(source)
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "semantic")
        self.assertEqual(diag.type, "TYPE_MISMATCH_DECL")
        self.assertEqual(diag.symbol, "a")
        self.assertEqual(diag.expected, "int")
        self.assertEqual(diag.actual, "bool")

    def test_type_mismatch_assignment_literal(self):
        source = "int x = 1;\nx = true;"
        ast, st, diag = self._analyze_source(source)
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "semantic")
        self.assertEqual(diag.type, "TYPE_MISMATCH_ASSIGN")
        self.assertEqual(diag.symbol, "x")
        self.assertEqual(diag.expected, "int")
        self.assertEqual(diag.actual, "bool")

    def test_type_mismatch_assignment_variable(self):
        source = "int x = 1;\nbool flag = true;\nx = flag;"
        ast, st, diag = self._analyze_source(source)
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "semantic")
        self.assertEqual(diag.type, "TYPE_MISMATCH_ASSIGN")
        self.assertEqual(diag.symbol, "x")
        self.assertEqual(diag.expected, "int")
        self.assertEqual(diag.actual, "bool")

if __name__ == '__main__':
    unittest.main()
