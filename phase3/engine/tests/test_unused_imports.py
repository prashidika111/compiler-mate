"""Unit tests for UnusedImportAnalyzer."""
import unittest
from compilermate_engine.models import InvestigationRequest, DocumentInput, DiagnosticInput, Range, Position
from compilermate_engine.analyzers.unused_imports import UnusedImportAnalyzer

class TestUnusedImportAnalyzer(unittest.TestCase):
    def test_single_unused_import_line(self):
        code = "import os\n\ndef main():\n    print('hello')\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="'os' is not accessed",
                code="reportUnusedImport",
                range=Range(start=Position(line=0, character=7), end=Position(line=0, character=9))
            )
        )
        res = UnusedImportAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "UNUSED_IMPORT")
        self.assertEqual(len(res.candidate_fixes), 1)
        fix = res.candidate_fixes[0]
        self.assertIn(fix.verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(fix.edits[0].new_text, "")

    def test_from_import_multiple_names(self):
        code = "from math import sqrt, sin, cos\n\nval = sqrt(4) + cos(0)\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="'sin' is imported but unused",
                code="F401",
                range=Range(start=Position(line=0, character=23), end=Position(line=0, character=26))
            )
        )
        res = UnusedImportAnalyzer.analyze(req.diagnostic, req.document)
        self.assertIsNotNone(res)
        self.assertEqual(res.category, "UNUSED_IMPORT")
        self.assertEqual(len(res.candidate_fixes), 1)
        fix = res.candidate_fixes[0]
        self.assertIn(fix.verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertIn("sqrt, cos", fix.edits[0].new_text)

if __name__ == "__main__":
    unittest.main()
