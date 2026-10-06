import unittest
from compilermate.diagnostics import Diagnostic

class TestDiagnostic(unittest.TestCase):
    def test_syntax_diagnostic_fields(self):
        d = Diagnostic(
            phase="syntax",
            type="MISSING_TOKEN",
            line=1,
            column=10,
            expected=";",
            actual="EOF",
            message="Expected ';' after expression"
        )
        self.assertEqual(d.phase, "syntax")
        self.assertEqual(d.type, "MISSING_TOKEN")
        self.assertEqual(d.line, 1)
        self.assertEqual(d.column, 10)
        self.assertEqual(d.expected, ";")
        self.assertEqual(d.actual, "EOF")
        self.assertIn("Expected ';'", d.message)
        self.assertIsNone(d.symbol)

    def test_semantic_diagnostic_fields(self):
        d = Diagnostic(
            phase="semantic",
            type="REDECLARATION",
            line=2,
            column=1,
            expected="unique identifier",
            actual="x already declared as int at line 1",
            message="Identifier 'x' is already declared",
            symbol="x"
        )
        self.assertEqual(d.phase, "semantic")
        self.assertEqual(d.type, "REDECLARATION")
        self.assertEqual(d.line, 2)
        self.assertEqual(d.column, 1)
        self.assertEqual(d.symbol, "x")
        self.assertEqual(d.expected, "unique identifier")
        self.assertEqual(d.actual, "x already declared as int at line 1")

    def test_lexical_diagnostic_fields(self):
        d = Diagnostic(
            phase="lexical",
            type="INVALID_CHARACTER",
            line=1,
            column=7,
            expected="valid token",
            actual="@",
            message="Unrecognized character '@'"
        )
        self.assertEqual(d.phase, "lexical")
        self.assertEqual(d.type, "INVALID_CHARACTER")
        self.assertEqual(d.line, 1)
        self.assertEqual(d.column, 7)
        self.assertEqual(d.expected, "valid token")
        self.assertEqual(d.actual, "@")
        self.assertIn("Unrecognized character", d.message)
        self.assertIsNone(d.symbol)

if __name__ == '__main__':
    unittest.main()
