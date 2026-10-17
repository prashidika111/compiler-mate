"""Automated regression suite verifying all six canonical demonstration scenarios."""
from __future__ import annotations
import unittest
from compilermate_engine.models import (
    InvestigationRequest,
    DocumentInput,
    DiagnosticInput,
    Range,
    Position
)
from compilermate_engine.investigator import DiagnosticInvestigator

class TestDemonstrationScenarios(unittest.TestCase):
    """End-to-end test cases verifying all six demonstration scenarios."""

    def test_scenario_1_unclosed_delimiter(self):
        code = "def run_scenario_1():\n    numbers = [10, 20, 30\n    def next_step():\n        return 42\n    pass\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///demo_scenarios.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: invalid syntax",
                range=Range(start=Position(line=2, character=4), end=Position(line=2, character=7)),
                severity=1,
                source="Python"
            )
        )
        res = DiagnosticInvestigator.investigate(req)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.category, "UNCLOSED_DELIMITER")
        self.assertIn("secondary symptom", res.explanation.cause_vs_symptom.lower())
        self.assertGreaterEqual(len(res.candidate_fixes), 1)
        self.assertIn(res.candidate_fixes[0].verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertTrue(bool(res.candidate_fixes[0].diff))
        self.assertEqual(res.metadata.get("analysis_backend"), "python_diagnostic_rules")
        self.assertTrue(res.metadata.get("rule_based"))
        self.assertEqual(len(res.metadata.get("source_sha256", "")), 64)

    def test_scenario_2_missing_colon(self):
        code = "def run_scenario_2(value: int):\n    if value > 100\n        print('Large value')\n    pass\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///demo_scenarios.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: expected ':'",
                range=Range(start=Position(line=1, character=18), end=Position(line=1, character=18)),
                severity=1,
                source="Python"
            )
        )
        res = DiagnosticInvestigator.investigate(req)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.category, "MISSING_COLON")
        self.assertGreaterEqual(len(res.candidate_fixes), 1)
        self.assertIn(res.candidate_fixes[0].verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertIn(":", res.candidate_fixes[0].edits[0].new_text)

    def test_scenario_3_expected_indented_block(self):
        code = "def empty_worker_handler():\nprint('Next handler')\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///demo_scenarios.py", text=code),
            diagnostic=DiagnosticInput(
                message="IndentationError: expected an indented block after function definition on line 1",
                range=Range(start=Position(line=1, character=0), end=Position(line=1, character=5)),
                severity=1,
                source="Python"
            )
        )
        res = DiagnosticInvestigator.investigate(req)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.category, "INDENTATION_EXPECTED_BLOCK")
        self.assertGreaterEqual(len(res.candidate_fixes), 1)
        self.assertIn(res.candidate_fixes[0].verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])

    def test_scenario_4_unterminated_string_literal(self):
        code = "def run_scenario_4():\n    welcome_banner = \"Welcome to CompilerMate Phase 3\n    print(welcome_banner)\n    pass\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///demo_scenarios.py", text=code),
            diagnostic=DiagnosticInput(
                message="SyntaxError: unterminated string literal",
                range=Range(start=Position(line=1, character=21), end=Position(line=1, character=53)),
                severity=1,
                source="Python"
            )
        )
        res = DiagnosticInvestigator.investigate(req)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.category, "UNTERMINATED_STRING")
        self.assertGreaterEqual(len(res.candidate_fixes), 1)
        self.assertIn(res.candidate_fixes[0].verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertIn("\"", res.candidate_fixes[0].edits[0].new_text)

    def test_scenario_5_undefined_name_typo(self):
        code = "def run_scenario_5():\n    record_count = 50\n    return record_cont + 10\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///demo_scenarios.py", text=code),
            diagnostic=DiagnosticInput(
                message="'record_cont' is not defined",
                range=Range(start=Position(line=2, character=11), end=Position(line=2, character=22)),
                severity=1,
                source="Python"
            )
        )
        res = DiagnosticInvestigator.investigate(req)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.category, "UNDEFINED_NAME")
        self.assertGreaterEqual(len(res.candidate_fixes), 1)
        self.assertIn(res.candidate_fixes[0].verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(res.candidate_fixes[0].edits[0].new_text, "record_count")

    def test_scenario_6_unused_import(self):
        code = "import os\n\ndef run():\n    pass\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///demo_scenarios.py", text=code),
            diagnostic=DiagnosticInput(
                message="'os' is not accessed",
                code="reportUnusedImport",
                range=Range(start=Position(line=0, character=7), end=Position(line=0, character=9)),
                severity=2,
                source="Pylance"
            )
        )
        res = DiagnosticInvestigator.investigate(req)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.category, "UNUSED_IMPORT")
        self.assertGreaterEqual(len(res.candidate_fixes), 1)
        self.assertIn(res.candidate_fixes[0].verification.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(res.candidate_fixes[0].edits[0].new_text, "")

if __name__ == "__main__":
    unittest.main()
