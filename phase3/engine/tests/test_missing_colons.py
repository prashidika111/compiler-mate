"""Unit tests for MissingColonAnalyzer."""
import unittest
from compilermate_engine.models import InvestigationRequest, DocumentInput, DiagnosticInput, Range, Position
from compilermate_engine.analyzers.missing_colons import MissingColonAnalyzer

class TestMissingColonAnalyzer(unittest.TestCase):
    def test_missing_colon_in_def(self):
        code = "def add(a, b)\n    return a + b\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: expected ':'",
                range=Range(start=Position(line=0, character=14), end=Position(line=0, character=14))
            )
        )
        res = MissingColonAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "MISSING_COLON")
        self.assertEqual(res.metadata["keyword"], "def")
        self.assertEqual(len(res.candidate_fixes), 1)
        fix = res.candidate_fixes[0]
        self.assertIn(fix.verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(fix.edits[0].new_text, ":")
        self.assertEqual(fix.edits[0].range.start.line, 0)
        self.assertEqual(fix.edits[0].range.start.character, 13)

    def test_missing_colon_in_if_with_comment(self):
        code = "if x > 10 # check threshold\n    print(x)\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: expected ':'",
                range=Range(start=Position(line=0, character=9), end=Position(line=0, character=9))
            )
        )
        res = MissingColonAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "MISSING_COLON")
        self.assertEqual(res.metadata["keyword"], "if")
        fix = res.candidate_fixes[0]
        # Colon must be inserted BEFORE the comment!
        self.assertEqual(fix.edits[0].range.start.character, 9)
        self.assertEqual(fix.edits[0].new_text, ":")

    def test_missing_colon_in_for_loop(self):
        code = "for item in items\n    process(item)\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: invalid syntax",
                range=Range(start=Position(line=0, character=17), end=Position(line=0, character=17))
            )
        )
        res = MissingColonAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "MISSING_COLON")
        self.assertEqual(res.metadata["keyword"], "for")
        self.assertIn(res.candidate_fixes[0].verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])

if __name__ == "__main__":
    unittest.main()
