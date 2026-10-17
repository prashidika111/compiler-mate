"""Analyzer for unmatched or unclosed delimiters and cause-vs-symptom syntax errors."""
from __future__ import annotations
import io
import tokenize
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

MATCHING_PAIRS = {
    '(': ')',
    '[': ']',
    '{': '}'
}
REVERSE_PAIRS = {
    ')': '(',
    ']': '[',
    '}': '{'
}

class DelimiterAnalyzer:
    """Investigates unclosed and mismatched delimiters and distinguishes
    the root cause (earlier open bracket/paren) from the symptom (later SyntaxError).
    """

    @classmethod
    def can_handle(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> bool:
        msg = diagnostic.message.lower()
        if (
            "syntaxerror" in msg
            or "invalid syntax" in msg
            or "unmatched" in msg
            or "was never closed" in msg
            or "was not closed" in msg
            or "not closed" in msg
            or "unclosed" in msg
        ):
            return True
        if "closing parenthesis" in msg or ("expected" in msg and any(c in msg for c in "()[]{}")):
            return True
        # Also check if tokenization detects unclosed delimiter regardless of message
        return False

    @classmethod
    def analyze(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> Optional[InvestigationResult]:
        text = document.text
        lines = text.splitlines(keepends=True)
        diag_line_0 = diagnostic.range.start.line
        diag_line_1 = diag_line_0 + 1

        # Track delimiter stack: (char, line_1, col_0, line_content)
        stack: List[Tuple[str, int, int, str]] = []
        mismatched_closer: Optional[Tuple[str, int, int, str, str]] = None  # (found, line, col, line_content, expected)

        try:
            tokens = list(tokenize.tokenize(io.BytesIO(text.encode('utf-8')).readline))
        except tokenize.TokenError as te:
            # TokenError often says ('EOF in multi-line statement', (line, col))
            # Fallback to character scanner if tokenize fails early
            tokens = []
        except Exception:
            tokens = []

        if tokens:
            for tok in tokens:
                if tok.type == tokenize.OP:
                    val = tok.string
                    if val in MATCHING_PAIRS:
                        line_text = lines[tok.start[0] - 1] if tok.start[0] - 1 < len(lines) else ""
                        stack.append((val, tok.start[0], tok.start[1], line_text))
                    elif val in REVERSE_PAIRS:
                        if stack and stack[-1][0] == REVERSE_PAIRS[val]:
                            stack.pop()
                        else:
                            expected = MATCHING_PAIRS.get(stack[-1][0]) if stack else "nothing (extra closing delimiter)"
                            line_text = lines[tok.start[0] - 1] if tok.start[0] - 1 < len(lines) else ""
                            mismatched_closer = (val, tok.start[0], tok.start[1], line_text, expected)
                            break
        else:
            # Simple fallback token-level scanner ignoring strings/comments
            stack, mismatched_closer = cls._fallback_scan(text)

        # Case 1: Mismatched closer encountered
        if mismatched_closer:
            found_char, m_line_1, m_col_0, m_line_text, expected_desc = mismatched_closer
            evidence = [
                EvidenceItem(
                    title=f"Mismatched delimiter '{found_char}'",
                    line=m_line_1,
                    column=m_col_0 + 1,
                    snippet=m_line_text.strip(),
                    annotation=f"Found closing delimiter '{found_char}', but expected {expected_desc}."
                )
            ]

            candidate_fixes = []
            if stack and stack[-1][0] in MATCHING_PAIRS:
                expected_char = MATCHING_PAIRS[stack[-1][0]]
                rep_edit = [
                    SourceEdit(
                        range=Range(
                            start=Position(line=m_line_1 - 1, character=m_col_0),
                            end=Position(line=m_line_1 - 1, character=m_col_0 + 1)
                        ),
                        new_text=expected_char
                    )
                ]
                v_rep, p_rep = FixVerifier.verify(text, rep_edit, diagnostic.message)
                candidate_fixes.append(CandidateFix(
                    id="fix-replace-mismatched-closer",
                    title=f"Replace '{found_char}' with '{expected_char}' on line {m_line_1}",
                    description=f"Changes the mismatched closing delimiter '{found_char}' to '{expected_char}' to match '{stack[-1][0]}'.",
                    edits=rep_edit,
                    verification=v_rep,
                    diff=FixVerifier.generate_diff(text, p_rep)
                ))
            else:
                del_edit = [
                    SourceEdit(
                        range=Range(
                            start=Position(line=m_line_1 - 1, character=m_col_0),
                            end=Position(line=m_line_1 - 1, character=m_col_0 + 1)
                        ),
                        new_text=""
                    )
                ]
                v_del, p_del = FixVerifier.verify(text, del_edit, diagnostic.message)
                candidate_fixes.append(CandidateFix(
                    id="fix-remove-unmatched-closer",
                    title=f"Remove extra '{found_char}' on line {m_line_1}",
                    description=f"Deletes the extraneous closing delimiter '{found_char}'.",
                    edits=del_edit,
                    verification=v_del,
                    diff=FixVerifier.generate_diff(text, p_del)
                ))

            explanation = Explanation(
                summary=f"Mismatched delimiter: '{found_char}' at line {m_line_1} does not match open delimiter.",
                details=f"The closing delimiter '{found_char}' at line {m_line_1}, column {m_col_0 + 1} was encountered, but expected {expected_desc}.",
                cause_vs_symptom="The diagnostic is located directly at the mismatched delimiter.",
                next_steps=f"Replace '{found_char}' with the expected closer or remove it if extra."
            )

            return InvestigationResult(
                status="success",
                category="MISMATCHED_DELIMITER",
                diagnostic=diagnostic,
                explanation=explanation,
                evidence=evidence,
                candidate_fixes=candidate_fixes,
                metadata={"found_char": found_char, "line": m_line_1}
            )

        # Case 2: Unclosed delimiter on stack
        if stack:
            top_char, top_line_1, top_col_0, top_line_text = stack[-1]
            expected_closer = MATCHING_PAIRS[top_char]
            is_cause_vs_symptom = (diag_line_1 > top_line_1)

            cause_symptom_text = (
                f"The compiler reported a SyntaxError at line {diag_line_1}, but this is a secondary symptom. "
                f"The root cause is an unclosed '{top_char}' opened earlier at line {top_line_1}, column {top_col_0 + 1}. "
                f"Python's parser remains inside the '{top_char}' construct and treats subsequent code as part of that expression."
                if is_cause_vs_symptom else
                f"The delimiter '{top_char}' opened at line {top_line_1}, column {top_col_0 + 1} was never closed before the end of the statement or file."
            )

            evidence = [
                EvidenceItem(
                    title=f"Unclosed opening delimiter '{top_char}'",
                    line=top_line_1,
                    column=top_col_0 + 1,
                    snippet=top_line_text.strip(),
                    annotation=f"Opening delimiter '{top_char}' was opened here and never closed."
                )
            ]

            if is_cause_vs_symptom and diag_line_0 < len(lines):
                diag_line_text = lines[diag_line_0].strip()
                evidence.append(EvidenceItem(
                    title="SyntaxError reported location (symptom)",
                    line=diag_line_1,
                    column=diagnostic.range.start.character + 1,
                    snippet=diag_line_text,
                    annotation="Parser encountered an unexpected token here while still expecting a closing delimiter."
                ))

            # Generate candidate fix: insert closing delimiter
            candidate_fixes: List[CandidateFix] = []

            # Option A: Close at the end of the line containing the opener
            opener_line_content = lines[top_line_1 - 1] if top_line_1 - 1 < len(lines) else ""
            trimmed_len = len(opener_line_content.rstrip('\r\n'))
            comment_idx = opener_line_content.find('#')
            insert_col = comment_idx if comment_idx != -1 else trimmed_len

            # If multiple delimiters are open, generate full closure first
            if len(stack) > 1:
                all_closers = "".join(MATCHING_PAIRS[c[0]] for c in reversed(stack))
                fix_all_edits = [
                    SourceEdit(
                        range=Range(
                            start=Position(line=top_line_1 - 1, character=insert_col),
                            end=Position(line=top_line_1 - 1, character=insert_col)
                        ),
                        new_text=all_closers
                    )
                ]
                v_all, p_all = FixVerifier.verify(text, fix_all_edits, diagnostic.message)
                candidate_fixes.append(CandidateFix(
                    id="fix-close-all-delimiters-opener-line",
                    title=f"Insert all closing delimiters '{all_closers}' on line {top_line_1}",
                    description=f"Closes all unclosed delimiters ('{''.join(c[0] for c in stack)}') with '{all_closers}'.",
                    edits=fix_all_edits,
                    verification=v_all,
                    diff=FixVerifier.generate_diff(text, p_all)
                ))

            fix_edits = [
                SourceEdit(
                    range=Range(
                        start=Position(line=top_line_1 - 1, character=insert_col),
                        end=Position(line=top_line_1 - 1, character=insert_col)
                    ),
                    new_text=expected_closer
                )
            ]

            verification, p_text = FixVerifier.verify(text, fix_edits, diagnostic.message)
            candidate_fixes.append(CandidateFix(
                id="fix-close-delimiter-opener-line",
                title=f"Insert closing '{expected_closer}' on line {top_line_1}",
                description=f"Closes the unclosed '{top_char}' at the end of line {top_line_1}.",
                edits=fix_edits,
                verification=verification,
                diff=FixVerifier.generate_diff(text, p_text)
            ))

            # Option B: If cause vs symptom, also try closing immediately before the symptom line
            if is_cause_vs_symptom and diag_line_0 < len(lines):
                closers_to_try = ["".join(MATCHING_PAIRS[c[0]] for c in reversed(stack))] if len(stack) > 1 else [expected_closer]
                for c_str in closers_to_try:
                    fix_edits_b = [
                        SourceEdit(
                            range=Range(
                                start=Position(line=diag_line_0, character=0),
                                end=Position(line=diag_line_0, character=0)
                            ),
                            new_text=f"{c_str}\n"
                        )
                    ]
                    verif_b, p_b = FixVerifier.verify(text, fix_edits_b, diagnostic.message)
                    if verif_b.status == "VERIFIED":
                        candidate_fixes.append(CandidateFix(
                            id=f"fix-close-delimiter-before-statement-{c_str}",
                            title=f"Insert closing '{c_str}' before line {diag_line_1}",
                            description=f"Closes the preceding block with '{c_str}' before line {diag_line_1}.",
                            edits=fix_edits_b,
                            verification=verif_b,
                            diff=FixVerifier.generate_diff(text, p_b)
                        ))

            explanation = Explanation(
                summary=f"Unclosed delimiter: opening '{top_char}' at line {top_line_1} has no matching '{expected_closer}'.",
                details=(
                    f"Python syntax requires every opening parenthesis '(', bracket '[', and brace '{{' "
                    f"to have a corresponding closing delimiter. When an opener is left unclosed, the parser "
                    f"continues scanning subsequent lines within that open context."
                ),
                cause_vs_symptom=cause_symptom_text,
                next_steps=f"Add the matching '{expected_closer}' to close the expression."
            )

            return InvestigationResult(
                status="success",
                category="UNCLOSED_DELIMITER",
                diagnostic=diagnostic,
                explanation=explanation,
                evidence=evidence,
                candidate_fixes=candidate_fixes,
                metadata={"unclosed_char": top_char, "expected_closer": expected_closer, "cause_line": top_line_1}
            )

        return None

    @classmethod
    def _fallback_scan(cls, text: str) -> Tuple[List[Tuple[str, int, int, str]], Optional[Tuple[str, int, int, str, str]]]:
        """Simple character scan skipping single-line strings and comments."""
        lines = text.splitlines(keepends=True)
        stack: List[Tuple[str, int, int, str]] = []
        for line_idx, line in enumerate(lines):
            in_str: Optional[str] = None
            for col_idx, ch in enumerate(line):
                if in_str:
                    if ch == in_str and (col_idx == 0 or line[col_idx - 1] != '\\'):
                        in_str = None
                    continue
                if ch in ('"', "'"):
                    in_str = ch
                    continue
                if ch == '#':
                    break
                if ch in MATCHING_PAIRS:
                    stack.append((ch, line_idx + 1, col_idx, line))
                elif ch in REVERSE_PAIRS:
                    if stack and stack[-1][0] == REVERSE_PAIRS[ch]:
                        stack.pop()
                    else:
                        exp = MATCHING_PAIRS.get(stack[-1][0], "nothing") if stack else "nothing"
                        return stack, (ch, line_idx + 1, col_idx, line, exp)
        return stack, None
