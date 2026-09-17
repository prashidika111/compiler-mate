import unittest
from compilermate.diagnostics import Diagnostic

class TestDiagnostic(unittest.TestCase):
    def test_fields(self):
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

if __name__ == '__main__':
    unittest.main()
