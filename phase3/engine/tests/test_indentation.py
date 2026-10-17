"""Unit tests for IndentationAnalyzer."""
import unittest
from compilermate_engine.models import InvestigationRequest, DocumentInput, DiagnosticInput, Range, Position
from compilermate_engine.analyzers.indentation import IndentationAnalyzer

class TestIndentationAnalyzer(unittest.TestCase):
    def test_expected_indented_block_empty_function(self):
        code = "def do_nothing():\nprint('done')\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="IndentationError: expected an indented block after function definition on line 1",
                range=Range(start=Position(line=1, character=0), end=Position(line=1, character=5))
            )
        )
        res = IndentationAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "INDENTATION_EXPECTED_BLOCK")
        self.assertTrue(len(res.candidate_fixes) >= 1)
        # Should offer fix with pass or indenting print
        verified = [f for f in res.candidate_fixes if f.verification.status in ["PARTIALLY_VERIFIED", "VERIFIED"]]
        self.assertTrue(len(verified) >= 1)

    def test_unexpected_indent(self):
        code = "x = 10\n    y = 20\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="IndentationError: unexpected indent",
                range=Range(start=Position(line=1, character=4), end=Position(line=1, character=5))
            )
        )
        res = IndentationAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "INDENTATION_UNEXPECTED")
        self.assertEqual(len(res.candidate_fixes), 1)
        self.assertIn(res.candidate_fixes[0].verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(res.candidate_fixes[0].edits[0].new_text, "")

    def test_unindent_mismatch(self):
        code = "def foo():\n    x = 1\n   y = 2\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="IndentationError: unindent does not match any outer indentation level",
                range=Range(start=Position(line=2, character=3), end=Position(line=2, character=4))
            )
        )
        res = IndentationAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "INDENTATION_UNINDENT_MISMATCH")
        self.assertTrue(len(res.candidate_fixes) >= 1)

if __name__ == "__main__":
    unittest.main()
