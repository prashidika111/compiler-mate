"""Unit tests for DelimiterAnalyzer."""
import unittest
from compilermate_engine.models import InvestigationRequest, DocumentInput, DiagnosticInput, Range, Position
from compilermate_engine.analyzers.delimiters import DelimiterAnalyzer

class TestDelimiterAnalyzer(unittest.TestCase):
    def test_single_unclosed_bracket(self):
        code = "items = [1, 2, 3\nprint(items)\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: invalid syntax",
                range=Range(start=Position(line=1, character=0), end=Position(line=1, character=5))
            )
        )
        res = DelimiterAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "UNCLOSED_DELIMITER")
        self.assertIn("Unclosed delimiter", res.explanation.summary)
        self.assertTrue(len(res.candidate_fixes) >= 1)
        # Check verified fix exists (partially verified by static compiler checks)
        verified_fixes = [f for f in res.candidate_fixes if f.verification.status in ["PARTIALLY_VERIFIED", "VERIFIED"]]
        self.assertTrue(len(verified_fixes) >= 1)
        self.assertIn("]", verified_fixes[0].edits[0].new_text)

    def test_cause_vs_symptom_distinction(self):
        code = "total = sum([1, 2, 3\ndef compute():\n    return 42\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: invalid syntax",
                range=Range(start=Position(line=1, character=0), end=Position(line=1, character=3))
            )
        )
        res = DelimiterAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertIn("secondary symptom", res.explanation.cause_vs_symptom)
        self.assertIn("root cause", res.explanation.cause_vs_symptom)
        self.assertEqual(res.metadata["cause_line"], 1)
        # Multi-delimiter closure should be verified
        verified = [f for f in res.candidate_fixes if f.verification.status in ["PARTIALLY_VERIFIED", "VERIFIED"]]
        self.assertTrue(len(verified) >= 1)

    def test_mismatched_closer(self):
        code = "values = [1, 2, 3)\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: closing parenthesis ')' does not match opening bracket '['",
                range=Range(start=Position(line=0, character=17), end=Position(line=0, character=18))
            )
        )
        res = DelimiterAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "MISMATCHED_DELIMITER")
        self.assertEqual(res.metadata["found_char"], ")")

if __name__ == "__main__":
    unittest.main()
