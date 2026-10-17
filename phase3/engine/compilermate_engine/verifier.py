from __future__ import annotations
import ast
import difflib
import io
import tokenize
from typing import List, Tuple, Optional, Dict, Any
from .models import SourceEdit, VerificationResult, VerificationCheck, VerificationReport

def apply_edits_to_text(text: str, edits: List[SourceEdit]) -> str:
    """Apply a list of 0-based source edits to a text string.
    Sorts edits in reverse order so character offsets don't invalidate subsequent edits.
    """
    lines = text.splitlines(keepends=True)
    if not lines and text:
        lines = [text]
    elif not lines and not text:
        lines = [""]

    # Calculate 0-based character offsets for each line
    line_offsets: List[int] = [0]
    cur = 0
    for l in lines:
        cur += len(l)
        line_offsets.append(cur)

    def pos_to_offset(line_idx: int, char_idx: int) -> int:
        if line_idx >= len(lines):
            return len(text)
        base = line_offsets[line_idx]
        line_len = len(lines[line_idx])
        return min(base + char_idx, base + line_len)

    # Convert edits to character slices (start_offset, end_offset, new_text)
    converted: List[Tuple[int, int, str]] = []
    for edit in edits:
        s_off = pos_to_offset(edit.range.start.line, edit.range.start.character)
        e_off = pos_to_offset(edit.range.end.line, edit.range.end.character)
        converted.append((s_off, e_off, edit.new_text))

    # Sort descending by start offset
    converted.sort(key=lambda x: (x[0], x[1]), reverse=True)

    result = text
    for s_off, e_off, new_text in converted:
        result = result[:s_off] + new_text + result[e_off:]

    return result

class FixVerifier:
    """Verifies proposed source edits using Python's compiler, AST facilities, and deterministic tests."""

    @classmethod
    def verify(
        cls,
        original_text: str,
        edits: List[SourceEdit],
        original_diagnostic_message: str = "",
        test_command: Optional[str] = None,
        cwd: Optional[str] = None,
        run_tests: bool = False
    ) -> Tuple[VerificationResult, str]:
        """Verifies edits on original_text.
        Returns (VerificationResult, patched_text).
        """
        checks: List[VerificationCheck] = []
        unresolved_risks: List[str] = []

        try:
            patched_text = apply_edits_to_text(original_text, edits)
        except Exception as e:
            checks.append(VerificationCheck(
                name="Apply Edits",
                passed=False,
                status="FAILED",
                message=f"Failed to apply edits cleanly: {e}"
            ))
            unresolved_risks.append("Proposed edits could not be applied cleanly to source buffer.")
            return VerificationResult(
                status="FAILED",
                checks=checks,
                limitation="Edits could not be applied to source buffer.",
                unresolved_risks=unresolved_risks
            ), original_text

        # 1. Tokenizer validation
        token_ok = True
        try:
            tokens = list(tokenize.tokenize(io.BytesIO(patched_text.encode('utf-8')).readline))
            checks.append(VerificationCheck(
                name="Lexical Tokenization",
                passed=True,
                status="PASSED",
                message="Source tokenized cleanly without lexical tokenization errors."
            ))
        except tokenize.TokenError as te:
            token_ok = False
            checks.append(VerificationCheck(
                name="Lexical Tokenization",
                passed=False,
                status="FAILED",
                message=f"Tokenization error in patched source: {te}"
            ))
            unresolved_risks.append(f"Lexical token error remains: {te}")
        except Exception as e:
            token_ok = False
            checks.append(VerificationCheck(
                name="Lexical Tokenization",
                passed=False,
                status="FAILED",
                message=f"Tokenization failed: {e}"
            ))
            unresolved_risks.append(f"Tokenization exception: {e}")

        # 2. AST Parse validation
        ast_ok = True
        try:
            tree = ast.parse(patched_text, filename="<CompilerMate-Verify>")
            checks.append(VerificationCheck(
                name="AST Syntax Parse",
                passed=True,
                status="PASSED",
                message="Patched source forms a valid Python Abstract Syntax Tree."
            ))
        except SyntaxError as se:
            ast_ok = False
            checks.append(VerificationCheck(
                name="AST Syntax Parse",
                passed=False,
                status="FAILED",
                message=f"SyntaxError remaining at line {se.lineno}: {se.msg}"
            ))
            unresolved_risks.append(f"SyntaxError remaining at line {se.lineno}: {se.msg}")
        except Exception as e:
            ast_ok = False
            checks.append(VerificationCheck(
                name="AST Syntax Parse",
                passed=False,
                status="FAILED",
                message=f"AST parse failed: {e}"
            ))
            unresolved_risks.append(f"AST parse failure: {e}")

        # 3. Bytecode Compilation
        compile_ok = True
        if ast_ok:
            try:
                compile(patched_text, filename="<CompilerMate-Verify>", mode="exec")
                checks.append(VerificationCheck(
                    name="Bytecode Compilation",
                    passed=True,
                    status="PASSED",
                    message="Python bytecode compiled successfully without compiler-level errors."
                ))
            except SyntaxError as se:
                compile_ok = False
                checks.append(VerificationCheck(
                    name="Bytecode Compilation",
                    passed=False,
                    status="FAILED",
                    message=f"Compiler rejected source at line {se.lineno}: {se.msg}"
                ))
                unresolved_risks.append(f"Compiler rejected source at line {se.lineno}: {se.msg}")
            except Exception as e:
                compile_ok = False
                checks.append(VerificationCheck(
                    name="Bytecode Compilation",
                    passed=False,
                    status="FAILED",
                    message=f"Bytecode compilation failed: {e}"
                ))
                unresolved_risks.append(f"Bytecode compilation failure: {e}")

        # 4. Optional automated test runner
        test_passed: Optional[bool] = None
        if run_tests and test_command:
            t_check = cls.run_test_check(test_command, cwd=cwd)
            checks.append(t_check)
            test_passed = t_check.passed
            if not t_check.passed:
                unresolved_risks.append(f"Automated test failed: {t_check.message}")
        else:
            checks.append(VerificationCheck(
                name="Automated Test Execution",
                passed=False,
                status="NOT_CHECKED",
                message="Automated tests not executed (run independently to verify semantic correctness)."
            ))
            unresolved_risks.append("Dynamic runtime behavior and test suite have not been executed.")

        if token_ok and ast_ok and compile_ok:
            if test_passed is True:
                status = "PASSED"
                limitation = "Fully verified: Static checks passed and automated test suite passed."
            elif test_passed is False:
                status = "FAILED"
                limitation = "Syntax is valid, but automated test execution failed."
            else:
                # Static compiler checks passed, tests unperformed
                status = "PARTIALLY_VERIFIED"
                limitation = "Static verification confirms lexical, syntactic, and bytecode validity; automated tests were not executed."
                unresolved_risks.append("Semantic correctness and developer intent are unconfirmed.")
        elif ast_ok and not compile_ok:
            status = "FAILED"
            limitation = "AST parsed successfully but bytecode compilation encountered errors."
        else:
            status = "FAILED"
            limitation = "Patched source still contains syntax or lexical errors."

        return VerificationResult(
            status=status,
            checks=checks,
            limitation=limitation,
            unresolved_risks=unresolved_risks
        ), patched_text

    @classmethod
    def run_test_check(
        cls,
        test_command: str,
        cwd: Optional[str] = None,
        timeout_seconds: float = 8.0
    ) -> VerificationCheck:
        """Executes a test command deterministically, capturing status and outputs."""
        import subprocess
        import time

        start_time = time.time()
        try:
            proc = subprocess.run(
                test_command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            duration_ms = round((time.time() - start_time) * 1000, 2)
            passed = (proc.returncode == 0)
            status = "PASSED" if passed else "FAILED"
            msg = (
                f"Test command '{test_command}' exited with code {proc.returncode}."
                if passed
                else f"Test command '{test_command}' failed with exit code {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip() or 'Test failure'}"
            )
            return VerificationCheck(
                name="Automated Test Execution",
                passed=passed,
                status=status,
                message=msg,
                command=test_command,
                exit_code=proc.returncode,
                stdout=proc.stdout[:2000] if proc.stdout else "",
                stderr=proc.stderr[:2000] if proc.stderr else "",
                duration_ms=duration_ms
            )
        except subprocess.TimeoutExpired as te:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            return VerificationCheck(
                name="Automated Test Execution",
                passed=False,
                status="FAILED",
                message=f"Test command timed out after {timeout_seconds}s.",
                command=test_command,
                exit_code=None,
                stdout=te.stdout[:1000] if te.stdout else "",
                stderr=te.stderr[:1000] if te.stderr else "",
                duration_ms=duration_ms
            )
        except Exception as exc:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            return VerificationCheck(
                name="Automated Test Execution",
                passed=False,
                status="UNABLE_TO_VERIFY",
                message=f"Unable to execute test command '{test_command}': {exc}",
                command=test_command,
                exit_code=None,
                duration_ms=duration_ms
            )

    @classmethod
    def compare_diagnostics(
        cls,
        original_text: str,
        patched_text: str,
        original_diagnostic_line_1: Optional[int] = None
    ) -> Tuple[List[str], List[str], List[str]]:
        """Compares syntax diagnostics between original and patched text.
        Returns (resolved_descriptions, remaining_descriptions, new_descriptions).
        """
        resolved: List[str] = []
        remaining: List[str] = []
        new_errs: List[str] = []

        # Parse original
        orig_err: Optional[Tuple[int, str]] = None
        try:
            ast.parse(original_text, filename="<original>")
        except SyntaxError as se:
            orig_err = (se.lineno or 1, se.msg)

        # Parse patched
        patch_err: Optional[Tuple[int, str]] = None
        try:
            ast.parse(patched_text, filename="<patched>")
        except SyntaxError as se:
            patch_err = (se.lineno or 1, se.msg)

        if orig_err:
            orig_line, orig_msg = orig_err
            if patch_err:
                patch_line, patch_msg = patch_err
                if patch_line == orig_line:
                    remaining.append(f"Line {patch_line}: {patch_msg}")
                else:
                    resolved.append(f"Line {orig_line}: {orig_msg}")
                    new_errs.append(f"Line {patch_line}: {patch_msg}")
            else:
                resolved.append(f"Line {orig_line}: {orig_msg}")
        elif original_diagnostic_line_1:
            if patch_err:
                patch_line, patch_msg = patch_err
                if patch_line == original_diagnostic_line_1:
                    remaining.append(f"Line {patch_line}: {patch_msg}")
                else:
                    new_errs.append(f"Line {patch_line}: {patch_msg}")
            else:
                resolved.append(f"Line {original_diagnostic_line_1}: Diagnostic resolved")

        return resolved, remaining, new_errs

    @classmethod
    def generate_diff(cls, original_text: str, patched_text: str) -> str:
        """Generates a clean unified diff between original and patched source."""
        orig_lines = original_text.splitlines(keepends=True)
        patch_lines = patched_text.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            orig_lines,
            patch_lines,
            fromfile="current",
            tofile="proposed_fix",
            n=2
        ))
        return "".join(diff_lines)
