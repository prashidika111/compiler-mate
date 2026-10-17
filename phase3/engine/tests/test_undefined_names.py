"""Unit tests for UndefinedNameAnalyzer."""
import unittest
from compilermate_engine.models import InvestigationRequest, DocumentInput, DiagnosticInput, Range, Position
from compilermate_engine.analyzers.undefined_names import UndefinedNameAnalyzer

class TestUndefinedNameAnalyzer(unittest.TestCase):
    def test_variable_typo_correction(self):
        code = "counter = 10\ntotal = countr + 5\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="'countr' is not defined",
                code="reportUndefinedVariable",
                range=Range(start=Position(line=1, character=8), end=Position(line=1, character=14))
            )
        )
        res = UndefinedNameAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "UNDEFINED_NAME")
        self.assertIn("counter", res.metadata["close_matches"])
        self.assertTrue(len(res.candidate_fixes) >= 1)
        fix = res.candidate_fixes[0]
        self.assertIn(fix.verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(fix.edits[0].new_text, "counter")

    def test_builtin_typo_correction(self):
        code = "prnt('Hello, world!')\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="NameError: name 'prnt' is not defined",
                range=Range(start=Position(line=0, character=0), end=Position(line=0, character=4))
            )
        )
        res = UndefinedNameAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "UNDEFINED_NAME")
        self.assertIn("print", res.metadata["close_matches"])
        fix = res.candidate_fixes[0]
        self.assertIn(fix.verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(fix.edits[0].new_text, "print")

    def test_missing_stdlib_import(self):
        code = "val = math.sqrt(16)\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="'math' is not defined",
                range=Range(start=Position(line=0, character=6), end=Position(line=0, character=10))
            )
        )
        res = UndefinedNameAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "UNDEFINED_NAME")
        self.assertTrue(res.metadata["is_stdlib_module"])
        fix = res.candidate_fixes[0]
        self.assertIn(fix.verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(fix.edits[0].new_text, "import math\n")

if __name__ == "__main__":
    unittest.main()
