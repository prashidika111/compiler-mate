"""Unit tests for UnterminatedStringAnalyzer."""
import unittest
from compilermate_engine.models import InvestigationRequest, DocumentInput, DiagnosticInput, Range, Position
from compilermate_engine.analyzers.strings import UnterminatedStringAnalyzer

class TestUnterminatedStringAnalyzer(unittest.TestCase):
    def test_unterminated_double_quote(self):
        code = 'greeting = "Hello, world\nprint(greeting)\n'
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: unterminated string literal (detected at line 1)",
                range=Range(start=Position(line=0, character=11), end=Position(line=0, character=24))
            )
        )
        res = UnterminatedStringAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "UNTERMINATED_STRING")
        self.assertEqual(len(res.candidate_fixes), 1)
        fix = res.candidate_fixes[0]
        self.assertIn(fix.verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(fix.edits[0].new_text, '"')

    def test_unterminated_single_quote(self):
        code = "msg = 'unclosed text\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: unterminated string literal (detected at line 1)",
                range=Range(start=Position(line=0, character=6), end=Position(line=0, character=20))
            )
        )
        res = UnterminatedStringAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "UNTERMINATED_STRING")
        self.assertIn(res.candidate_fixes[0].verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(res.candidate_fixes[0].edits[0].new_text, "'")

if __name__ == "__main__":
    unittest.main()
