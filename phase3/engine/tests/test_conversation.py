"""Unit tests for CompilerMate two-way conversation engine."""
from __future__ import annotations
import unittest
from compilermate_engine.models import (
    InteractionRequest,
    InteractionResponse,
    DocumentInput,
    DiagnosticInput,
    ChatMessage,
    Range,
    Position
)
from compilermate_engine.conversation import ConversationEngine

class TestConversationEngine(unittest.TestCase):
    """Test suite for contextual two-way developer-compiler dialogue."""

    def setUp(self):
        self.doc = DocumentInput(
            uri="file:///test.py",
            text="numbers = [10, 20, 30\ndef next_step():\n    return 42\n"
        )
        self.diag = DiagnosticInput(
            message="SyntaxError: invalid syntax",
            range=Range(start=Position(line=1, character=0), end=Position(line=1, character=3)),
            severity=1,
            source="Python"
        )
        self.inv_result = {
            "status": "success",
            "category": "UNCLOSED_DELIMITER",
            "diagnostic": {
                "message": "SyntaxError: invalid syntax",
                "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 3}}
            },
            "explanation": {
                "summary": "Unclosed delimiter: opening '[' at line 1 has no matching ']'.",
                "details": "Python syntax requires every opening bracket to be closed.",
                "cause_vs_symptom": "The delimiter '[' opened at line 1 was never closed."
            },
            "evidence": [
                {
                    "title": "Unclosed opening delimiter '['",
                    "line": 1,
                    "column": 11,
                    "snippet": "numbers = [10, 20, 30",
                    "annotation": "Opening delimiter '[' was opened here and never closed."
                },
                {
                    "title": "SyntaxError reported location (symptom)",
                    "line": 2,
                    "column": 1,
                    "snippet": "def next_step():",
                    "annotation": "Parser halted here."
                }
            ],
            "candidate_fixes": [
                {
                    "id": "fix-close-delimiter-opener-line",
                    "title": "Insert closing ']' on line 1",
                    "description": "Closes bracket at end of line 1",
                    "edits": [],
                    "verification": {"status": "VERIFIED", "checks": [{"name": "AST Syntax Parse", "passed": True}]},
                    "diff": "--- current\n+++ proposed\n+numbers = [10, 20, 30]\n"
                },
                {
                    "id": "fix-close-delimiter-before-statement",
                    "title": "Insert closing ']' before line 2",
                    "description": "Closes bracket before next statement",
                    "edits": [],
                    "verification": {"status": "VERIFIED", "checks": [{"name": "AST Syntax Parse", "passed": True}]},
                    "diff": "--- current\n+++ proposed\n+]\ndef next_step():\n"
                }
            ]
        }

    def _make_req(self, user_msg: str, history=None) -> InteractionRequest:
        return InteractionRequest(
            command="interact",
            document=self.doc,
            diagnostic=self.diag,
            investigation_result=self.inv_result,
            user_message=user_msg,
            history=history or []
        )

    def test_root_cause_inquiry(self):
        req = self._make_req("Why is this the root cause?")
        res = ConversationEngine.respond(req)
        self.assertEqual(res.status, "success")
        self.assertIn("pushdown stack", res.message.lower())
        self.assertIn("delimiter", res.message.lower())

    def test_evidence_clarification(self):
        req = self._make_req("Explain the evidence for that conclusion")
        res = ConversationEngine.respond(req)
        self.assertEqual(res.status, "success")
        self.assertIn("Unclosed opening delimiter", res.message)
        self.assertIn("Line 1", res.message)
        self.assertIn("Line 2", res.message)

    def test_cause_vs_symptom_inquiry(self):
        req = self._make_req("Why does the error appear on this line when the actual problem is earlier?")
        res = ConversationEngine.respond(req)
        self.assertEqual(res.status, "success")
        self.assertIn("lookahead", res.message.lower())
        self.assertIn("Line 1", res.message)
        self.assertIn("Line 2", res.message)

    def test_simpler_terms(self):
        req = self._make_req("Can you explain this in simpler terms?")
        res = ConversationEngine.respond(req)
        self.assertEqual(res.status, "success")
        self.assertIn("In Simpler Terms", res.message)
        self.assertIn("bracket", res.message.lower())

    def test_alternative_fixes_selection(self):
        req = self._make_req("What alternative fixes are possible?")
        res = ConversationEngine.respond(req)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.action, "select_fix")
        self.assertIsNotNone(res.selected_fix_id)
        self.assertIn("Available Candidate Corrections", res.message)

    def test_tradeoffs_comparison(self):
        req = self._make_req("What are the trade-offs between these fixes?")
        res = ConversationEngine.respond(req)
        self.assertEqual(res.status, "success")
        self.assertIn("Trade-offs", res.message)
        self.assertIn("Option 1", res.message)
        self.assertIn("Option 2", res.message)

    def test_apply_impact_inquiry(self):
        req = self._make_req("What happens if I apply this correction?")
        res = ConversationEngine.respond(req)
        self.assertEqual(res.status, "success")
        self.assertIn("WorkspaceEdit", res.message)
        self.assertIn("VERIFIED", res.message)
        self.assertIn("diff", res.message.lower())

    def test_reinvestigate_request(self):
        req = self._make_req("Can you investigate the issue again after my changes?")
        res = ConversationEngine.respond(req)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.action, "reinvestigate")


    def test_stale_source_snapshot_requests_reinvestigation(self):
        import hashlib
        self.inv_result["metadata"] = {
            "source_sha256": hashlib.sha256(self.doc.text.encode("utf-8")).hexdigest()
        }
        self.doc.text += "# changed after investigation\n"
        res = ConversationEngine.respond(self._make_req("Why is this the root cause?"))
        self.assertEqual(res.status, "success")
        self.assertEqual(res.action, "reinvestigate")
        self.assertIn("document has changed", res.message.lower())

    def test_empty_message_handling(self):
        req = self._make_req("   ")
        res = ConversationEngine.respond(req)
        self.assertEqual(res.status, "error")

    def test_multi_turn_history(self):
        h = [
            ChatMessage(role="user", content="Why is this line 2?"),
            ChatMessage(role="assistant", content="Because of lookahead latency.")
        ]
        req = self._make_req("And what is the evidence?", history=h)
        res = ConversationEngine.respond(req)
        self.assertEqual(res.status, "success")
        self.assertIn("evidence", res.message.lower())

if __name__ == "__main__":
    unittest.main()
