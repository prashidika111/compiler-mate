"""Analyzer for Python indentation errors."""
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

class IndentationAnalyzer:
    """Investigates IndentationError diagnostics:
    - expected an indented block
    - unexpected indent
    - unindent does not match any outer indentation level
    """

    @classmethod
    def can_handle(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> bool:
        msg = diagnostic.message.lower()
        return "indentationerror" in msg or "indent" in msg or "expected an indented block" in msg

    @classmethod
    def _detect_indent_unit(cls, lines: List[str]) -> str:
        """Determines prevailing indentation unit (e.g., 4 spaces, 2 spaces, or tab)."""
        for line in lines:
            if line.startswith('\t'):
                return '\t'
            spaces = len(line) - len(line.lstrip(' '))
            if spaces in (2, 4):
                return ' ' * spaces
        return '    '

    @classmethod
    def _get_leading_whitespace(cls, line: str) -> str:
        return line[:len(line) - len(line.lstrip())]

    @classmethod
    def analyze(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> Optional[InvestigationResult]:
        lines = document.text.splitlines(keepends=True)
        diag_line_0 = diagnostic.range.start.line
        diag_line_1 = diag_line_0 + 1
        msg = diagnostic.message.lower()

        indent_unit = cls._detect_indent_unit(lines)

        # Subcase A: Expected an indented block
        if "expected an indented block" in msg or ("expected" in msg and "block" in msg):
            # Look backwards from diagnostic line to find the header with ':'
            header_line_0: Optional[int] = None
            for idx in range(diag_line_0, -1, -1):
                if idx < len(lines):
                    stripped = lines[idx].split('#')[0].strip()
                    if stripped.endswith(':'):
                        header_line_0 = idx
                        break

            if header_line_0 is None:
                header_line_0 = max(0, diag_line_0 - 1)

            header_line_1 = header_line_0 + 1
            header_raw = lines[header_line_0] if header_line_0 < len(lines) else ""
            header_indent = cls._get_leading_whitespace(header_raw)
            body_indent = header_indent + indent_unit

            evidence = [
                EvidenceItem(
                    title="Compound statement header requiring body block",
                    line=header_line_1,
                    column=len(header_indent) + 1,
                    snippet=header_raw.strip(),
                    annotation=f"Header ends with ':' and requires an indented statement block immediately following."
                )
            ]

            candidate_fixes: List[CandidateFix] = []

            # If diagnostic line has code that is simply not indented enough
            if diag_line_0 < len(lines) and diag_line_0 > header_line_0 and lines[diag_line_0].strip():
                cur_line = lines[diag_line_0]
                cur_indent = cls._get_leading_whitespace(cur_line)
                indent_edit = [
                    SourceEdit(
                        range=Range(
                            start=Position(line=diag_line_0, character=0),
                            end=Position(line=diag_line_0, character=len(cur_indent))
                        ),
                        new_text=body_indent
                    )
                ]
                v_indent, p_indent = FixVerifier.verify(document.text, indent_edit, diagnostic.message)
                if v_indent.status == "VERIFIED":
                    candidate_fixes.append(CandidateFix(
                        id=f"fix-indent-line-{diag_line_1}",
                        title=f"Indent line {diag_line_1} by {len(body_indent)} spaces",
                        description=f"Indents the statement on line {diag_line_1} into the body of the '{header_raw.strip()}' block.",
                        edits=indent_edit,
                        verification=v_indent,
                        diff=FixVerifier.generate_diff(document.text, p_indent)
                    ))

            # Option B: Insert 'pass' statement
            insert_line_0 = header_line_0 + 1
            pass_text = f"{body_indent}pass\n"
            pass_edits = [
                SourceEdit(
                    range=Range(
                        start=Position(line=insert_line_0, character=0),
                        end=Position(line=insert_line_0, character=0)
                    ),
                    new_text=pass_text
                )
            ]
            v_pass, p_pass = FixVerifier.verify(document.text, pass_edits, diagnostic.message)
            candidate_fixes.append(CandidateFix(
                id=f"fix-insert-pass-block-{header_line_1}",
                title="Insert placeholder 'pass' statement in empty block",
                description=f"Adds an indented 'pass' statement under '{header_raw.strip()}' on line {header_line_1 + 1}.",
                edits=pass_edits,
                verification=v_pass,
                diff=FixVerifier.generate_diff(document.text, p_pass)
            ))

            explanation = Explanation(
                summary=f"Expected an indented block after statement on line {header_line_1}.",
                details=(
                    f"In Python, code blocks under compound statement headers (such as def, if, for, class) "
                    f"are defined by indentation rather than curly braces. Every block header ending in ':' "
                    f"must be followed by at least one indented statement."
                ),
                cause_vs_symptom=f"The block starting on line {header_line_1} was left empty or subsequent code was not indented.",
                next_steps="Provide an indented statement or insert 'pass' if the block is intentionally empty."
            )

            return InvestigationResult(
                status="success",
                category="INDENTATION_EXPECTED_BLOCK",
                diagnostic=diagnostic,
                explanation=explanation,
                evidence=evidence,
                candidate_fixes=candidate_fixes,
                metadata={"header_line": header_line_1, "body_indent": body_indent}
            )

        # Subcase B: Unexpected indent
        if "unexpected indent" in msg:
            offending_raw = lines[diag_line_0] if diag_line_0 < len(lines) else ""
            offending_indent = cls._get_leading_whitespace(offending_raw)

            # Look for previous non-empty line's indentation
            prev_indent = ""
            prev_line_1 = diag_line_0
            for idx in range(diag_line_0 - 1, -1, -1):
                if lines[idx].strip():
                    prev_indent = cls._get_leading_whitespace(lines[idx])
                    prev_line_1 = idx + 1
                    break

            evidence = [
                EvidenceItem(
                    title="Unexpectedly indented statement",
                    line=diag_line_1,
                    column=len(offending_indent) + 1,
                    snippet=offending_raw.strip(),
                    annotation=f"Line has {len(offending_indent)} spaces of indentation with no preceding compound block."
                )
            ]

            candidate_fixes = []
            fix_edits = [
                SourceEdit(
                    range=Range(
                        start=Position(line=diag_line_0, character=0),
                        end=Position(line=diag_line_0, character=len(offending_indent))
                    ),
                    new_text=prev_indent
                )
            ]
            v_fix, p_fix = FixVerifier.verify(document.text, fix_edits, diagnostic.message)
            candidate_fixes.append(CandidateFix(
                id=f"fix-realign-indent-{diag_line_1}",
                title=f"Re-align indentation to match line {prev_line_1} ({len(prev_indent)} spaces)",
                description=f"Removes the unexpected indentation from line {diag_line_1}.",
                edits=fix_edits,
                verification=v_fix,
                diff=FixVerifier.generate_diff(document.text, p_fix)
            ))

            explanation = Explanation(
                summary=f"Unexpected indent on line {diag_line_1}.",
                details="Python does not permit increasing indentation unless introduced by a compound statement header ending with a colon ':'.",
                cause_vs_symptom=f"Line {diag_line_1} is indented further than permitted by the surrounding block structure.",
                next_steps=f"Align this line's indentation with the surrounding block ({len(prev_indent)} spaces)."
            )

            return InvestigationResult(
                status="success",
                category="INDENTATION_UNEXPECTED",
                diagnostic=diagnostic,
                explanation=explanation,
                evidence=evidence,
                candidate_fixes=candidate_fixes,
                metadata={"offending_line": diag_line_1}
            )

        # Subcase C: Unindent does not match any outer indentation level
        if "unindent" in msg or "outer indentation level" in msg:
            offending_raw = lines[diag_line_0] if diag_line_0 < len(lines) else ""
            offending_indent = cls._get_leading_whitespace(offending_raw)

            # Collect valid outer indentation levels from preceding lines
            valid_levels: List[Tuple[int, str]] = []
            for idx in range(diag_line_0 - 1, -1, -1):
                if lines[idx].strip():
                    ind = cls._get_leading_whitespace(lines[idx])
                    if (len(ind), ind) not in valid_levels:
                        valid_levels.append((len(ind), ind))

            evidence = [
                EvidenceItem(
                    title="Mismatched unindentation",
                    line=diag_line_1,
                    column=len(offending_indent) + 1,
                    snippet=offending_raw.strip(),
                    annotation=f"Current indentation ({len(offending_indent)} spaces) does not align with any enclosing block."
                )
            ]

            candidate_fixes = []
            # Propose matching the closest outer level
            if valid_levels:
                # Find the closest level
                closest_len, closest_ind = min(valid_levels, key=lambda x: abs(x[0] - len(offending_indent)))
                fix_edits = [
                    SourceEdit(
                        range=Range(
                            start=Position(line=diag_line_0, character=0),
                            end=Position(line=diag_line_0, character=len(offending_indent))
                        ),
                        new_text=closest_ind
                    )
                ]
                v_fix, p_fix = FixVerifier.verify(document.text, fix_edits, diagnostic.message)
                candidate_fixes.append(CandidateFix(
                    id=f"fix-align-outer-indent-{diag_line_1}",
                    title=f"Adjust indentation to match outer block ({closest_len} spaces)",
                    description=f"Aligns line {diag_line_1} with the enclosing scope's indentation level.",
                    edits=fix_edits,
                    verification=v_fix,
                    diff=FixVerifier.generate_diff(document.text, p_fix)
                ))

            explanation = Explanation(
                summary=f"Unindent does not match outer indentation level at line {diag_line_1}.",
                details="When exiting an indented block, the unindented line must exactly match the column of an outer enclosing block.",
                cause_vs_symptom=f"Line {diag_line_1} is indented {len(offending_indent)} spaces, which does not match any enclosing scope level.",
                next_steps="Adjust the indentation to match an enclosing block (e.g. 0 or 4 spaces)."
            )

            return InvestigationResult(
                status="success",
                category="INDENTATION_UNINDENT_MISMATCH",
                diagnostic=diagnostic,
                explanation=explanation,
                evidence=evidence,
                candidate_fixes=candidate_fixes,
                metadata={"offending_line": diag_line_1}
            )

        return None
