"""Unit tests for engine IPC and protocol serialization."""
import io
import json
import subprocess
import sys
import unittest
from compilermate_engine.models import InvestigationRequest, DocumentInput, DiagnosticInput, Range, Position
from compilermate_engine.investigator import DiagnosticInvestigator

class TestIPCAndProtocol(unittest.TestCase):
    def test_unsupported_diagnostic_handling(self):
        code = "print(123)\n"
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri="file:///test.py", text=code),
            diagnostic=DiagnosticInput(
                message="Unknown custom linter error XYZ",
                range=Range(start=Position(line=0, character=0), end=Position(line=0, character=5))
            )
        )
        res = DiagnosticInvestigator.investigate(req)
        self.assertEqual(res.status, "unsupported")
        self.assertEqual(res.category, "UNSUPPORTED")
        self.assertEqual(len(res.candidate_fixes), 0)
        self.assertIn("No safe deterministic fix", res.explanation.details)

    def test_cli_ipc_stdin_stdout_subprocess(self):
        payload = {
            "command": "investigate",
            "document": {
                "uri": "file:///script.py",
                "text": "def calculate(a, b)\n    return a + b\n"
            },
            "diagnostic": {
                "message": "SyntaxError: expected ':'",
                "range": {
                    "start": { "line": 0, "character": 14 },
                    "end": { "line": 0, "character": 14 }
                }
            }
        }
        proc = subprocess.run(
            [sys.executable, "-m", "compilermate_engine.cli"],
            input=json.dumps(payload),
            text=True,
            capture_output=True
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["category"], "MISSING_COLON")
        self.assertTrue(len(data["candidate_fixes"]) >= 1)
        self.assertIsNotNone(data["candidate_fixes"][0].get("diff"))
        self.assertIn("+def calculate(a, b):", data["candidate_fixes"][0]["diff"])

    def test_cli_malformed_json_handling(self):
        proc = subprocess.run(
            [sys.executable, "-m", "compilermate_engine.cli"],
            input="{not valid json...",
            text=True,
            capture_output=True
        )
        self.assertNotEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["status"], "error")
    def test_cli_verify_ipc(self):
        payload = {
            "command": "verify",
            "document": {
                "uri": "file:///script.py",
                "text": "def calculate(a, b)\n    return a + b\n"
            },
            "diagnostic": {
                "message": "SyntaxError: expected ':'",
                "range": {
                    "start": { "line": 0, "character": 19 },
                    "end": { "line": 0, "character": 19 }
                }
            },
            "edits": [
                {
                    "range": {
                        "start": { "line": 0, "character": 19 },
                        "end": { "line": 0, "character": 19 }
                    },
                    "new_text": ":"
                }
            ],
            "run_tests": False
        }
        proc = subprocess.run(
            [sys.executable, "-m", "compilermate_engine.cli"],
            input=json.dumps(payload),
            text=True,
            capture_output=True
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["status"], "success")
        self.assertIn("verification_report", data)
        report = data["verification_report"]
        self.assertEqual(report["status"], "PARTIALLY_VERIFIED")
        self.assertTrue(len(report["checks"]) >= 3)
        self.assertIn("def calculate(a, b):", data["patched_text"])
        self.assertIn("+def calculate(a, b):", data["diff"])

if __name__ == "__main__":
    unittest.main()
