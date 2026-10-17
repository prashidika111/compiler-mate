"""Unit tests for FixVerifier and apply_edits_to_text."""
import unittest
from compilermate_engine.models import SourceEdit, Range, Position
from compilermate_engine.verifier import apply_edits_to_text, FixVerifier

class TestFixVerifier(unittest.TestCase):
    def test_apply_single_insertion(self):
        text = "def foo()\n    pass\n"
        edits = [
            SourceEdit(
                range=Range(start=Position(line=0, character=9), end=Position(line=0, character=9)),
                new_text=":"
            )
        ]
        result = apply_edits_to_text(text, edits)
        self.assertEqual(result, "def foo():\n    pass\n")

    def test_apply_multiple_edits_preserves_order(self):
        text = "a = 1\nb = 2\n"
        edits = [
            SourceEdit(
                range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
                new_text="first"
            ),
            SourceEdit(
                range=Range(start=Position(line=1, character=0), end=Position(line=1, character=1)),
                new_text="second"
            )
        ]
        result = apply_edits_to_text(text, edits)
        self.assertEqual(result, "first = 1\nsecond = 2\n")

    def test_verify_valid_python(self):
        text = "x = [1, 2, 3\n"
        edits = [
            SourceEdit(
                range=Range(start=Position(line=0, character=12), end=Position(line=0, character=12)),
                new_text="]"
            )
        ]
        verif, patched = FixVerifier.verify(text, edits)
        # Static checks pass without tests -> PARTIALLY_VERIFIED
        self.assertIn(verif.status, ["PARTIALLY_VERIFIED", "VERIFIED"])
        self.assertEqual(patched, "x = [1, 2, 3]\n")
        # Tokenize, AST, and Bytecode passed
        syntax_checks = [c for c in verif.checks if c.name != "Automated Test Execution"]
        self.assertTrue(all(c.passed for c in syntax_checks))
        self.assertIn("Static verification confirms", verif.limitation)

    def test_verify_still_invalid_python(self):
        text = "x = [1, 2, 3\n"
        edits = [
            SourceEdit(
                range=Range(start=Position(line=0, character=12), end=Position(line=0, character=12)),
                new_text="}"  # Wrong closer!
            )
        ]
        verif, _ = FixVerifier.verify(text, edits)
        self.assertEqual(verif.status, "FAILED")
        self.assertTrue(any(not c.passed for c in verif.checks))

    def test_verify_with_passing_test_runner(self):
        text = "def answer():\n    return 4\n"
        edits = [
            SourceEdit(
                range=Range(start=Position(line=1, character=12), end=Position(line=1, character=13)),
                new_text="2"
            )
        ]
        # Command that succeeds
        cmd = 'python -c "assert True"'
        verif, patched = FixVerifier.verify(text, edits, test_command=cmd, run_tests=True)
        self.assertEqual(verif.status, "PASSED")
        self.assertIn("Fully verified", verif.limitation)
        test_check = next(c for c in verif.checks if c.name == "Automated Test Execution")
        self.assertTrue(test_check.passed)
        self.assertEqual(test_check.status, "PASSED")

    def test_verify_with_failing_test_runner(self):
        # Syntax compiles cleanly, but test fails
        text = "def answer():\n    return 41\n"
        edits = [
            SourceEdit(
                range=Range(start=Position(line=1, character=11), end=Position(line=1, character=13)),
                new_text="41"
            )
        ]
        # Command that fails
        cmd = 'python -c "assert False, \'Semantic test failure\'"'
        verif, patched = FixVerifier.verify(text, edits, test_command=cmd, run_tests=True)
        self.assertEqual(verif.status, "FAILED")
        self.assertIn("automated test execution failed", verif.limitation)
        test_check = next(c for c in verif.checks if c.name == "Automated Test Execution")
        self.assertFalse(test_check.passed)
        self.assertEqual(test_check.status, "FAILED")

    def test_compare_diagnostics_resolved(self):
        original = "numbers = [1, 2, 3\ndef foo(): pass\n"
        patched = "numbers = [1, 2, 3]\ndef foo(): pass\n"
        resolved, remaining, new_errs = FixVerifier.compare_diagnostics(original, patched, original_diagnostic_line_1=2)
        self.assertTrue(len(resolved) > 0)
        self.assertEqual(len(remaining), 0)
        self.assertEqual(len(new_errs), 0)

if __name__ == "__main__":
    unittest.main()
