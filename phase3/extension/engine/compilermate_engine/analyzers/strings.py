"""Analyzer for unterminated string literals in Python."""
from __future__ import annotations
import re
from typing import Optional, List, Tuple
from ..models import (
    DiagnosticInput,
    DocumentInput,
    EvidenceItem,
    Explanation,
    CandidateFix,
    SourceEdit,
    Range,
    Position,
    InvestigationResult
)
from ..verifier import FixVerifier

STRING_PREFIXES = ('r', 'u', 'f', 'b', 'rf', 'fr', 'rb', 'br')

class UnterminatedStringAnalyzer:
    """Investigates unterminated string literal syntax errors."""

    @classmethod
    def can_handle(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> bool:
        msg = diagnostic.message.lower()
        return "unterminated string literal" in msg or "eol while scanning string literal" in msg or "eof in multi-line statement" in msg

    @classmethod
    def analyze(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> Optional[InvestigationResult]:
        lines = document.text.splitlines(keepends=True)
        diag_line_0 = diagnostic.range.start.line
        diag_line_1 = diag_line_0 + 1

        target_line_0 = min(diag_line_0, max(0, len(lines) - 1))
        target_line_1 = target_line_0 + 1
        raw_line = lines[target_line_0] if target_line_0 < len(lines) else ""

        # Scan for unclosed string quote on target_line or earlier
        unclosed_quote: Optional[str] = None
        open_col: int = 0

        # Check for triple quote first
        if '"""' in raw_line and raw_line.count('"""') % 2 != 0:
            unclosed_quote = '"""'
            open_col = raw_line.rfind('"""')
        elif "'''" in raw_line and raw_line.count("'''") % 2 != 0:
            unclosed_quote = "'''"
            open_col = raw_line.rfind("'''")
        else:
            # Single or double quote
            # Simple quote scan tracking escapes
            for quote_type in ('"', "'"):
                # Count unescaped occurrences
                escaped = False
                in_quote = False
                last_open_idx = -1
                for idx, ch in enumerate(raw_line):
                    if escaped:
                        escaped = False
                        continue
                    if ch == '\\':
                        escaped = True
                        continue
                    if ch == quote_type:
                        if in_quote:
                            in_quote = False
                        else:
                            in_quote = True
                            last_open_idx = idx
                if in_quote:
                    unclosed_quote = quote_type
                    open_col = last_open_idx
                    break

        if not unclosed_quote:
            # Fallback: check if line ends without matching quote
            stripped = raw_line.rstrip('\r\n')
            if '"' in stripped and stripped.count('"') % 2 != 0:
                unclosed_quote = '"'
                open_col = stripped.rfind('"')
            elif "'" in stripped and stripped.count("'") % 2 != 0:
                unclosed_quote = "'"
                open_col = stripped.rfind("'")
            else:
                unclosed_quote = '"'
                open_col = len(stripped) - 1

        evidence = [
            EvidenceItem(
                title=f"Unterminated string literal ({unclosed_quote})",
                line=target_line_1,
                column=open_col + 1,
                snippet=raw_line.strip(),
                annotation=f"String literal opened with {unclosed_quote} was not closed before the end of the line."
            )
        ]

        # Candidate fix: insert closing quote at end of line (before newline)
        trimmed_len = len(raw_line.rstrip('\r\n'))
        fix_edits = [
            SourceEdit(
                range=Range(
                    start=Position(line=target_line_0, character=trimmed_len),
                    end=Position(line=target_line_0, character=trimmed_len)
                ),
                new_text=unclosed_quote
            )
        ]

        verification, p_text = FixVerifier.verify(document.text, fix_edits, diagnostic.message)

        candidate_fixes = [
            CandidateFix(
                id=f"fix-close-string-line-{target_line_1}",
                title=f"Insert closing {unclosed_quote} at end of line {target_line_1}",
                description=f"Closes the unterminated string literal on line {target_line_1} with a matching {unclosed_quote}.",
                edits=fix_edits,
                verification=verification,
                diff=FixVerifier.generate_diff(document.text, p_text)
            )
        ]

        explanation = Explanation(
            summary=f"Unterminated string literal on line {target_line_1}.",
            details=(
                f"Single-line string literals (enclosed in single or double quotes) cannot span multiple lines "
                f"unless enclosed in triple quotes (''' or \"\"\") or escaped with a backslash at the line end. "
                f"The string opened with {unclosed_quote} is missing its matching closing quote."
            ),
            cause_vs_symptom=f"Line {target_line_1} ends without closing the open {unclosed_quote} delimiter.",
            next_steps=f"Add a closing {unclosed_quote} before the newline, or convert to a triple-quoted string for multiline text."
        )

        return InvestigationResult(
            status="success",
            category="UNTERMINATED_STRING",
            diagnostic=diagnostic,
            explanation=explanation,
            evidence=evidence,
            candidate_fixes=candidate_fixes,
            metadata={"quote": unclosed_quote, "line": target_line_1}
        )
