"""Analyzer for missing colons in Python compound statements."""
from __future__ import annotations
import re
from typing import Optional, List
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

COMPOUND_KEYWORDS = (
    "if", "elif", "else", "def", "class", "for", "while", "with", "try", "except", "finally", "async def", "async for", "async with"
)

# Regex matching start of compound statement header
COMPOUND_PATTERN = re.compile(
    r"^\s*(?:async\s+)?(def|class|if|elif|else|for|while|with|try|except|finally)\b"
)

class MissingColonAnalyzer:
    """Investigates missing ':' syntax errors in compound statement headers."""

    @classmethod
    def can_handle(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> bool:
        msg = diagnostic.message.lower()
        if "expected ':'" in msg or "expected colon" in msg or "':'" in msg:
            return True
        if "syntaxerror" in msg or "invalid syntax" in msg:
            # Check line context
            lines = document.text.splitlines()
            diag_line_0 = diagnostic.range.start.line
            for offset in (0, -1):
                idx = diag_line_0 + offset
                if 0 <= idx < len(lines):
                    line_str = lines[idx].strip()
                    if COMPOUND_PATTERN.match(line_str) and not line_str.rstrip().endswith(':'):
                        return True
        return False

    @classmethod
    def analyze(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> Optional[InvestigationResult]:
        lines = document.text.splitlines(keepends=True)
        diag_line_0 = diagnostic.range.start.line

        target_line_0: Optional[int] = None
        matched_kw: Optional[str] = None

        # Check diagnostic line first, then preceding line (in case parser stopped on next line)
        for offset in (0, -1):
            idx = diag_line_0 + offset
            if 0 <= idx < len(lines):
                raw_line = lines[idx]
                code_part = raw_line.split('#')[0].rstrip()
                match = COMPOUND_PATTERN.match(code_part)
                if match:
                    # Verify it doesn't already end with a colon
                    if not code_part.endswith(':'):
                        target_line_0 = idx
                        matched_kw = match.group(1)
                        break

        if target_line_0 is None or matched_kw is None:
            return None

        target_line_1 = target_line_0 + 1
        raw_line = lines[target_line_0]
        # Calculate insertion column: end of code part before comment/newline
        comment_pos = raw_line.find('#')
        if comment_pos != -1:
            code_before_comment = raw_line[:comment_pos].rstrip()
            insert_col = len(code_before_comment)
        else:
            insert_col = len(raw_line.rstrip('\r\n'))

        evidence = [
            EvidenceItem(
                title=f"Compound statement '{matched_kw}' header",
                line=target_line_1,
                column=insert_col + 1,
                snippet=raw_line.strip(),
                annotation=f"Python requires a colon ':' at the end of every '{matched_kw}' clause header."
            )
        ]

        fix_edits = [
            SourceEdit(
                range=Range(
                    start=Position(line=target_line_0, character=insert_col),
                    end=Position(line=target_line_0, character=insert_col)
                ),
                new_text=":"
            )
        ]

        verification, p_text = FixVerifier.verify(document.text, fix_edits, diagnostic.message)

        candidate_fixes = [
            CandidateFix(
                id=f"fix-add-colon-line-{target_line_1}",
                title=f"Insert ':' at end of '{matched_kw}' statement",
                description=f"Appends the missing colon ':' to complete the header on line {target_line_1}.",
                edits=fix_edits,
                verification=verification,
                diff=FixVerifier.generate_diff(document.text, p_text)
            )
        ]

        explanation = Explanation(
            summary=f"Missing colon in '{matched_kw}' statement header at line {target_line_1}.",
            details=(
                f"In Python, compound statements (such as 'def', 'if', 'for', 'while', 'class', etc.) "
                f"must terminate their header line with a colon ':'. The colon signals the start of the "
                f"subsequent indented block."
            ),
            cause_vs_symptom=f"The diagnostic was triggered directly by the missing ':' after the '{matched_kw}' header.",
            next_steps=f"Add ':' to the end of the statement header on line {target_line_1} before beginning the indented block."
        )

        return InvestigationResult(
            status="success",
            category="MISSING_COLON",
            diagnostic=diagnostic,
            explanation=explanation,
            evidence=evidence,
            candidate_fixes=candidate_fixes,
            metadata={"keyword": matched_kw, "line": target_line_1, "column": insert_col + 1}
        )
