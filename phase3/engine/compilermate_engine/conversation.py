"""Context-aware two-way conversational investigation engine for CompilerMate.

Enables multi-turn interactive dialogue between developer and compiler diagnostics
grounded entirely in static analysis context, AST/token evidence, and multi-stage verification.
Zero external cloud or LLM dependencies.
"""
from __future__ import annotations
import re
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from .models import (
    InteractionRequest,
    InteractionResponse,
    CandidateFix,
    EvidenceItem
)

class ConversationEngine:
    """Interprets developer queries and produces evidence-grounded contextual responses."""

    @classmethod
    def respond(cls, request: InteractionRequest) -> InteractionResponse:
        query = request.user_message.strip()
        if not query:
            return InteractionResponse(
                status="error",
                message="Please enter a question or follow-up request about this diagnostic.",
                error_message="Empty user message."
            )

        inv = request.investigation_result or {}
        # Conversations are only trustworthy while grounded in the same source
        # snapshot as the investigation. Never explain stale evidence as current.
        metadata = inv.get("metadata") or {}
        expected_hash = metadata.get("source_sha256")
        if expected_hash:
            current_hash = hashlib.sha256(request.document.text.encode("utf-8")).hexdigest()
            if current_hash != expected_hash:
                return InteractionResponse(
                    status="success",
                    message=(
                        "The document has changed since this investigation was produced. "
                        "I won't treat the previous evidence or fixes as current. Please "
                        "re-investigate the active document before asking follow-up questions."
                    ),
                    action="reinvestigate"
                )
        category = inv.get("category", "UNKNOWN")
        diag_dict = inv.get("diagnostic", {})
        diag_msg = diag_dict.get("message", request.diagnostic.message)
        diag_range = diag_dict.get("range", {})
        diag_line_0 = diag_range.get("start", {}).get("line", request.diagnostic.range.start.line)
        diag_line_1 = diag_line_0 + 1

        expl = inv.get("explanation") or {}
        summary = expl.get("summary", "")
        details = expl.get("details", "")
        cause_vs_symptom = expl.get("cause_vs_symptom", "")

        evidence: List[Dict[str, Any]] = inv.get("evidence", [])
        fixes: List[Dict[str, Any]] = inv.get("candidate_fixes", [])
        doc_text = request.document.text

        q_lower = query.lower()

        # Short keyword-first commands. Keep these distinct so the vocabulary changes behaviour.
        if q_lower in {"hint", "nudge", "clue", "give me a hint", "small hint", "don't tell me", "dont tell me"}:
            return InteractionResponse(status="success", message=cls._handle_hint(category, diag_msg, evidence))
        if q_lower in {"example", "examples", "demo", "show example", "give example"} or q_lower.startswith("example "):
            return InteractionResponse(status="success", message=cls._handle_example(category, diag_msg))
        if q_lower in {"trace", "walkthrough", "walk through", "flow", "show steps", "walk me through"}:
            return InteractionResponse(status="success", message=cls._handle_trace(category, diag_msg, evidence, diag_line_1))
        if q_lower in {"why", "cause", "root", "reason", "why here", "why this", "root cause", "what caused this", "why did this fail", "why did it fail", "why failed"}:
            return cls._handle_root_cause(category, cause_vs_symptom, summary, details, evidence, diag_line_1)
        if q_lower in {"explain", "meaning", "what", "explain this", "what happened", "what does this mean"}:
            return InteractionResponse(status="success", message=f"**What the diagnostic means**\n\n{summary or diag_msg}\n\n{details or 'The parser or analyzer found something that conflicts with Python syntax or the checks available for this issue.'}")
        if q_lower in {"simplify", "simple", "beginner", "eli5", "simpler", "plain english", "in simple terms"}:
            return cls._handle_simplify(category, diag_msg, summary, fixes)
        if q_lower in {"evidence", "proof", "show evidence", "show proof", "why should i believe this", "what evidence"}:
            return cls._handle_evidence(evidence, diag_msg)
        if q_lower in {"alternatives", "alternative", "options", "other", "show options", "another way", "show another", "what else"}:
            return cls._handle_alternative_fixes(fixes, category, q_lower)
        if q_lower in {"compare", "tradeoffs", "trade-offs", "compare options", "which is better"}:
            return cls._handle_tradeoffs(fixes, category)
        if q_lower in {"impact", "change", "what if", "what changed", "consequences", "side effects", "what changes"}:
            return cls._handle_apply_impact(fixes, category)
        if q_lower in {"diff", "patch", "show diff", "view diff", "code diff", "unified diff"}:
            return cls._handle_diff(fixes)
        if q_lower in {"verify", "verification", "check", "deterministic check", "how to verify", "did it work"}:
            return cls._handle_verify(fixes, inv)
        if q_lower in {"test", "tests", "run tests", "did tests pass", "did test pass", "automated tests"}:
            return cls._handle_tests(fixes, inv)
        if q_lower in {"history", "records", "saved", "saved investigations", "show history", "reopen"}:
            return cls._handle_history(inv)
        if q_lower in {"risks", "risk", "uncertainty", "uncertainties", "what remains unverified", "unverified risks"}:
            return cls._handle_risks(fixes, inv)
        if q_lower in {"next", "next steps", "what next", "what should i do", "what to do next"}:
            return cls._handle_next_steps(fixes, inv)
        if q_lower in {"fix", "correct", "repair", "show fix", "suggest fix", "smallest fix"}:
            if fixes:
                return InteractionResponse(status="success", message="**Suggested correction**\n\n" + str(fixes[0].get("title", "A candidate fix is available.")) + "\n\nReview the proposed diff above, run verification, then apply the fix when ready.")
            return InteractionResponse(status="success", message="No safe deterministic fix is available for this diagnostic. Inspect the evidence and diagnostic location.")
        if q_lower in {"investigate", "reinvestigate", "re-investigate", "recheck", "re-run", "refresh"}:
            return InteractionResponse(
                status="success",
                message="Re-evaluating active document buffer and language diagnostics. Re-running CompilerMate investigation...",
                action="reinvestigate"
            )

        # 1. Re-investigation request
        if cls._is_reinvestigate_request(q_lower):
            return InteractionResponse(
                status="success",
                message="Re-evaluating active document buffer and language diagnostics. Re-running CompilerMate investigation...",
                action="reinvestigate"
            )

        # 2. Alternative fixes inquiry / fix selection
        if cls._is_alternative_fixes_request(q_lower):
            return cls._handle_alternative_fixes(fixes, category, q_lower)

        # 3. Fix comparison & trade-offs
        if cls._is_tradeoffs_request(q_lower):
            return cls._handle_tradeoffs(fixes, category)

        # 4. What happens if I apply / Impact inquiry / What changed
        if cls._is_apply_impact_request(q_lower):
            return cls._handle_apply_impact(fixes, category)

        # 5. Cause vs. Symptom / Line Discrepancy inquiry
        if cls._is_cause_vs_symptom_request(q_lower):
            return cls._handle_cause_vs_symptom(category, cause_vs_symptom, evidence, diag_line_1)

        # 6. Root Cause inquiry / Why did this fail
        if cls._is_root_cause_request(q_lower):
            return cls._handle_root_cause(category, cause_vs_symptom, summary, details, evidence, diag_line_1)

        # 7. Evidence clarification
        if cls._is_evidence_request(q_lower):
            return cls._handle_evidence(evidence, diag_msg)

        # 8. Diff inquiry
        if cls._is_diff_request(q_lower):
            return cls._handle_diff(fixes)

        # 9. Verification inquiry
        if cls._is_verify_request(q_lower):
            return cls._handle_verify(fixes, inv)

        # 10. Tests inquiry
        if cls._is_tests_request(q_lower):
            return cls._handle_tests(fixes, inv)

        # 11. History inquiry
        if cls._is_history_request(q_lower):
            return cls._handle_history(inv)

        # 12. Risks / Unverified inquiry
        if cls._is_risks_request(q_lower):
            return cls._handle_risks(fixes, inv)

        # 13. Next steps inquiry
        if cls._is_next_request(q_lower):
            return cls._handle_next_steps(fixes, inv)

        # 14. Simpler / Plain English explanation
        if cls._is_simplify_request(q_lower):
            return cls._handle_simplify(category, diag_msg, summary, fixes)

        # 15. Contextual fallback for domain questions
        return cls._handle_general_query(query, category, diag_msg, evidence, fixes, doc_text)

    @classmethod
    def _handle_hint(cls, category: str, diag_msg: str, evidence: List[Dict[str, Any]]) -> str:
        snippet = next((ev.get("snippet", "") for ev in evidence if ev.get("snippet")), "")
        hints = {
            "MISSING_COLON": "Look at the end of the function or compound-statement header. Python expects a punctuation mark before the indented body begins.",
            "INDENTATION_EXPECTED_BLOCK": "Look at the line immediately after the header ending in a colon. Python expects the body to be indented.",
            "UNTERMINATED_STRING": "Check the opening quote and scan forward to see whether a matching closing quote appears before the line ends.",
            "UNCLOSED_DELIMITER": "Pair up the opening and closing parentheses, brackets, and braces. One opening delimiter may still be unmatched.",
        }
        if category == "UNSUPPORTED" and ("colon" in diag_msg.lower() or "expected ':'" in diag_msg.lower()):
            category = "MISSING_COLON"
        hint = hints.get(category, "Start with the diagnostic location and inspect the nearby code for the token or name Python expected.")
        return "**Hint**\n\n" + hint + (f"\n\nRelevant snippet: `{snippet}`" if snippet else "") + "\n\nTry finding the exact spot yourself first; ask `explain` when you want the full reasoning."

    @classmethod
    def _handle_example(cls, category: str, diag_msg: str) -> str:
        examples = {
            "MISSING_COLON": "`def greet(name):`\n    `print(name)`",
            "INDENTATION_EXPECTED_BLOCK": "`if ready:`\n    `start()`",
            "UNTERMINATED_STRING": '`message = "hello"`',
            "UNCLOSED_DELIMITER": "`items = [1, 2, 3]`",
        }
        return "**A minimal example**\n\n" + examples.get(category, f"This example illustrates the general shape of a valid statement related to `{diag_msg}`. Check the exact context before applying it.") + "\n\nUse this as a pattern, not as a replacement for your whole line."

    @classmethod
    def _handle_trace(cls, category: str, diag_msg: str, evidence: List[Dict[str, Any]], diag_line: int) -> str:
        location = evidence[0].get("line", diag_line) if evidence else diag_line
        snippet = evidence[0].get("snippet", "") if evidence else ""
        return (f"**Trace the diagnostic**\n\n1. The analyzer reports: `{diag_msg}`.\n"
                f"2. The relevant evidence points to line {location}.\n"
                f"3. The issue category is `{category}`; this determines which Python rule or static check is relevant.\n"
                + (f"4. Code evidence: `{snippet}`\n" if snippet else "")
                + "This is a trace of the available diagnostic evidence, not a runtime execution trace.")

    # --- Intent Detectors ---

    @classmethod
    def _is_reinvestigate_request(cls, q: str) -> bool:
        if "reinvestigate" in q or "re-investigate" in q or "recheck" in q or "re-run" in q:
            return True
        if "investigate" in q and "again" in q:
            return True
        if "check" in q and "again" in q:
            return True
        return False

    @classmethod
    def _is_alternative_fixes_request(cls, q: str) -> bool:
        keywords = [
            "alternative fix", "alternative correction", "other fix", "other fixes",
            "other option", "other options", "another fix", "another way", "is there another way",
            "second fix", "switch fix", "select fix", "alternative candidate", "what else can i do"
        ]
        return any(k in q for k in keywords)

    @classmethod
    def _is_tradeoffs_request(cls, q: str) -> bool:
        keywords = ["trade-off", "tradeoff", "trade off", "compare fix", "compare the fixes", "difference between", "which fix is better", "pros and cons"]
        return any(k in q for k in keywords)

    @classmethod
    def _is_apply_impact_request(cls, q: str) -> bool:
        keywords = [
            "what happens if i apply", "what does this fix do", "impact of applying", "impact of this fix",
            "will this break", "safe to apply", "what will change", "what changed", "what changes", "what has changed"
        ]
        return any(k in q for k in keywords)

    @classmethod
    def _is_cause_vs_symptom_request(cls, q: str) -> bool:
        keywords = [
            "why does the error appear on this line", "why error on line", "why line", "why different line",
            "why does the error line", "error line differ", "differ from", "differ", "different line",
            "problem is earlier", "reported on line", "symptom", "syntax error on next line", "why on line"
        ]
        return any(k in q for k in keywords)

    @classmethod
    def _is_root_cause_request(cls, q: str) -> bool:
        keywords = [
            "why is this the root cause", "root cause", "why did this happen",
            "what caused this", "explain the cause", "why is this an error", "how did this happen",
            "why did this fail", "why did it fail", "why failed", "why did the code fail"
        ]
        return any(k in q for k in keywords)

    @classmethod
    def _is_evidence_request(cls, q: str) -> bool:
        keywords = ["evidence", "proof", "prove it", "how do you know", "what evidence", "why do you think that", "show evidence"]
        return any(k in q for k in keywords)

    @classmethod
    def _is_diff_request(cls, q: str) -> bool:
        keywords = ["diff", "patch", "show diff", "view diff", "code diff", "unified diff", "see the diff", "show the diff"]
        return any(k in q for k in keywords)

    @classmethod
    def _is_verify_request(cls, q: str) -> bool:
        keywords = ["verify", "verification", "check fix", "verify fix", "deterministic check", "how to verify", "did it work", "did verify pass"]
        return any(k in q for k in keywords)

    @classmethod
    def _is_tests_request(cls, q: str) -> bool:
        keywords = ["test", "tests", "run test", "run tests", "did tests pass", "did test pass", "automated test", "test suite", "unit test"]
        return any(k in q for k in keywords)

    @classmethod
    def _is_history_request(cls, q: str) -> bool:
        keywords = ["history", "records", "saved investigation", "reopen", "past investigation", "record id", "saved record"]
        return any(k in q for k in keywords)

    @classmethod
    def _is_risks_request(cls, q: str) -> bool:
        keywords = ["risk", "risks", "uncertainty", "uncertainties", "what remains unverified", "unverified", "what is unverified", "unverified risk", "remaining risks"]
        return any(k in q for k in keywords)

    @classmethod
    def _is_next_request(cls, q: str) -> bool:
        keywords = ["next", "next step", "next steps", "what next", "what should i do", "what to do next", "how to proceed"]
        return any(k in q for k in keywords)

    @classmethod
    def _is_simplify_request(cls, q: str) -> bool:
        keywords = [
            "simpler terms", "simple terms", "explain simply", "for beginners",
            "plain english", "eli5", "what does this mean", "in simple words", "easy explanation"
        ]
        return any(k in q for k in keywords)

    # --- Handlers ---

    @classmethod
    def _handle_root_cause(
        cls,
        category: str,
        cause_vs_symptom: str,
        summary: str,
        details: str,
        evidence: List[Dict[str, Any]],
        diag_line: int
    ) -> InteractionResponse:
        cause_line = evidence[0].get("line", diag_line) if evidence else diag_line

        if category == "UNCLOSED_DELIMITER":
            msg = (
                f"**Root Cause Analysis for Unclosed Delimiter:**\n\n"
                f"1. **Lexical Stack State:** Python's parser maintains an internal pushdown stack of open delimiters (`(`, `[`, `{{`). "
                f"The delimiter opened at line {cause_line} was pushed to the stack but never popped by a matching closer.\n"
                f"2. **Grammar Invalidation:** Because the delimiter remained unclosed, the parser continued reading subsequent lines "
                f"as part of the unfinished expression. When it encountered subsequent statements (such as a function definition or statement boundary), "
                f"it could not legally integrate them into the open expression.\n"
                f"3. **Conclusion:** Even though Python halts at line {diag_line}, the true grammatical defect is the missing delimiter on line {cause_line}."
            )
        elif category == "MISSING_COLON":
            msg = (
                f"**Root Cause Analysis for Missing Colon:**\n\n"
                f"Python's formal grammar defines compound statements (`def`, `if`, `for`, `while`, `class`) with a mandatory header terminator: the colon (`:`). "
                f"The parser matched the statement header on line {cause_line}, but upon reaching the end of the line (or beginning of the body), "
                f"the expected `:` token was absent. Without the colon, the transition from the header state to the suite (body) state cannot occur."
            )
        elif category == "INDENTATION_EXPECTED_BLOCK":
            msg = (
                f"**Root Cause Analysis for Indentation Error:**\n\n"
                f"Python uses off-side rule indentation to define statement blocks. After line {cause_line}'s header ending in ':', "
                f"the lexical analyzer must emit an `INDENT` token before any statements in the suite. "
                f"The compiler found either an immediate `DEDENT`, an unindented statement, or end-of-file, violating the requirement that every compound header must own at least one indented child statement."
            )
        elif category == "UNTERMINATED_STRING":
            msg = (
                f"**Root Cause Analysis for Unterminated String:**\n\n"
                f"Single-line string literals (`\"` or `'`) in Python cannot span past a newline character (`\\n`) without an explicit escape backslash. "
                f"The lexical scanner on line {cause_line} encountered the newline token before encountering the closing quote character, triggering a lexical scan error."
            )
        elif category == "UNDEFINED_NAME":
            msg = (
                f"**Root Cause Analysis for Undefined Name:**\n\n"
                f"A symbol resolution pass across the document's Abstract Syntax Tree. "
                f"The referenced identifier does not exist in local, enclosing, global, or built-in scope. "
                f"By analyzing the symbol table, CompilerMate detected that this identifier closely resembles an existing defined variable with a small Levenshtein edit distance."
            )
        elif category == "UNUSED_IMPORT":
            msg = (
                f"**Root Cause Analysis for Unused Import:**\n\n"
                f"An AST visitor inspected every `ast.Name` reference throughout the file. "
                f"The import statement placed a name into the module namespace on line {cause_line}, but no subsequent expressions or statements in the entire file ever load or call that name."
            )
        else:
            msg = (
                f"**Root Cause Summary:**\n\n"
                f"{cause_vs_symptom or summary or details}\n\n"
                f"The compiler stopped parsing at line {diag_line} because the encountered tokens violated Python's syntax rules."
            )

        return InteractionResponse(status="success", message=msg)

    @classmethod
    def _handle_evidence(cls, evidence: List[Dict[str, Any]], diag_msg: str) -> InteractionResponse:
        if not evidence:
            return InteractionResponse(
                status="success",
                message=f"No isolated sub-tokens were extracted for this diagnostic. The reported issue is: `{diag_msg}`."
            )

        parts = ["**Source-code evidence:**\n"]
        for idx, ev in enumerate(evidence, 1):
            title = ev.get("title", f"Evidence #{idx}")
            line = ev.get("line", "?")
            col = ev.get("column", "?")
            snippet = ev.get("snippet", "")
            annotation = ev.get("annotation", "")
            kind = ev.get("kind", "OBSERVED")
            parts.append(f"{idx}. [{kind}] **{title}** (Line {line}, Column {col}):\n   ```python\n   {snippet}\n   ```\n   *Compiler context:* {annotation}\n")

        parts.append("This concrete source evidence was gathered directly by AST inspection and lexical tokenization, distinguishing Observed facts, Inferred hypotheses, and Unverified claims.")
        return InteractionResponse(status="success", message="\n".join(parts))

    @classmethod
    def _handle_cause_vs_symptom(
        cls,
        category: str,
        cause_vs_symptom: str,
        evidence: List[Dict[str, Any]],
        diag_line: int
    ) -> InteractionResponse:
        cause_line = evidence[0].get("line", diag_line) if evidence else diag_line

        msg = (
            f"**Why the Diagnostic Appears on Line {diag_line} Rather Than Line {cause_line}:**\n\n"
            f"This is known in compiler design as **lookahead latency** or a **secondary cascading symptom**:\n\n"
            f"- **The Omission (Root Cause):** Occurred on **Line {cause_line}**.\n"
            f"- **The Diagnostic (Symptom):** Reported on **Line {diag_line}**.\n\n"
            f"**How the Parser Operates:**\n"
            f"Compilers do not stop immediately when you make an omission—they continue consuming tokens as long as those tokens could theoretically fit inside the open grammar rule. "
            f"On line {cause_line}, the parser expected a closing delimiter or suite, but valid tokens could still follow. It was only on line {diag_line}, when encountering an incompatible keyword or construct, that all possible parse branches collapsed. "
            f"Therefore, the compiler flagged line {diag_line}, but fixing line {diag_line} without addressing line {cause_line} will not resolve the syntax error."
        )
        return InteractionResponse(status="success", message=msg)

    @classmethod
    def _handle_simplify(
        cls,
        category: str,
        diag_msg: str,
        summary: str,
        fixes: List[Dict[str, Any]]
    ) -> InteractionResponse:
        if category == "UNCLOSED_DELIMITER":
            plain = "You opened a bracket `[` or parenthesis `(` on an earlier line, but forgot to close it with `]` or `)`. Python got confused because it thought everything below it was still inside the brackets."
        elif category == "MISSING_COLON":
            plain = "In Python, statement lines like `if`, `def`, `for`, or `while` must always end with a colon `:`. You just need to add a `:` at the end of that line before your indented code."
        elif category == "INDENTATION_EXPECTED_BLOCK":
            plain = "You started a function or conditional block, but didn't put any indented code underneath it. Python requires at least one indented line (or the word `pass`) inside every block."
        elif category == "UNTERMINATED_STRING":
            plain = "You started a text string with quotes (`\"` or `'`), but reached the end of the line without typing the closing quote."
        elif category == "UNDEFINED_NAME":
            plain = "You typed a variable name that Python doesn't recognize. It looks like a simple spelling mistake for a variable you created earlier in the file."
        elif category == "UNUSED_IMPORT":
            plain = "You imported a module or function at the top of your file, but never actually used it anywhere in your code. You can safely remove it to clean up your code."
        else:
            plain = summary or diag_msg

        fix_hint = f" The recommended fix is: **{fixes[0].get('title')}**." if fixes else ""
        msg = f"**In Simpler Terms:**\n\n{plain}{fix_hint}"
        return InteractionResponse(status="success", message=msg)

    @classmethod
    def _handle_alternative_fixes(
        cls,
        fixes: List[Dict[str, Any]],
        category: str,
        q_lower: str
    ) -> InteractionResponse:
        if not fixes:
            return InteractionResponse(
                status="success",
                message="No candidate fixes are currently available for this diagnostic."
            )

        if len(fixes) == 1:
            fix = fixes[0]
            msg = (
                f"**Candidate Corrections for {category}:**\n\n"
                f"There is currently 1 verified deterministic correction available:\n\n"
                f"- **{fix.get('title')}**\n"
                f"  {fix.get('description')}\n"
                f"  *Verification Status:* `{fix.get('verification', {}).get('status')}`\n\n"
                f"No other distinct textual fix would be syntactically valid without changing program semantics."
            )
            return InteractionResponse(
                status="success",
                message=msg,
                action="select_fix",
                selected_fix_id=fix.get("id")
            )

        # Multiple fixes exist
        # Check if user asked for a specific one (e.g. "second fix", "fix 2", "other")
        selected_idx = 0
        if "second" in q_lower or "2" in q_lower or "other" in q_lower or "alternative" in q_lower:
            selected_idx = 1 if len(fixes) > 1 else 0

        selected_fix = fixes[selected_idx]
        parts = [
            f"**Available Candidate Corrections ({len(fixes)} options):**\n"
        ]
        for idx, f in enumerate(fixes):
            prefix = "👉 **Selected:** " if idx == selected_idx else "   "
            parts.append(
                f"{idx + 1}. {prefix}**{f.get('title')}** (ID: `{f.get('id')}`)\n"
                f"   {f.get('description')}\n"
                f"   *Verification:* `{f.get('verification', {}).get('status')}`\n"
            )

        parts.append(
            f"\nI have selected **Fix #{selected_idx + 1}: {selected_fix.get('title')}** as the active correction. "
            f"You can review its unified diff above and click **Apply Correction** when you are ready."
        )

        return InteractionResponse(
            status="success",
            message="\n".join(parts),
            action="select_fix",
            selected_fix_id=selected_fix.get("id")
        )

    @classmethod
    def _handle_tradeoffs(cls, fixes: List[Dict[str, Any]], category: str) -> InteractionResponse:
        if not fixes:
            return InteractionResponse(
                status="success",
                message="No candidate fixes available to compare."
            )

        if len(fixes) == 1:
            fix = fixes[0]
            msg = (
                f"**Trade-off Analysis:**\n\n"
                f"Only one deterministic fix is available: **{fix.get('title')}**.\n\n"
                f"- **Advantage:** Directly satisfies Python's grammar without altering surrounding logic.\n"
                f"- **Verification:** {fix.get('verification', {}).get('status')} across lexical, AST, and bytecode checks.\n"
                f"- **Semantic Impact:** Minimal local edit."
            )
            return InteractionResponse(status="success", message=msg)

        parts = [f"**Comparison & Trade-offs Between Candidate Fixes ({category}):**\n"]
        for idx, f in enumerate(fixes, 1):
            title = f.get("title", "")
            desc = f.get("description", "")
            verif = f.get("verification", {}).get("status", "UNVERIFIED")

            if "pass" in title.lower():
                pros = "Provides an immediate syntactic placeholder without assuming what logic belongs in the function body."
                cons = "Leaves the function body empty (no-op), requiring implementation later."
            elif "indent" in title.lower():
                pros = "Directly incorporates the following line of code into the compound statement's block."
                cons = "Alters control flow by making the next statement conditional or scoped to this header."
            elif "before line" in title.lower() or "opener" in title.lower():
                pros = "Closes delimiter immediately at the statement boundary, preserving expression locality."
                cons = "May alter the expression if subsequent items were intended to be inside."
            else:
                pros = "Resolves the immediate syntax/type diagnostic cleanly."
                cons = "Review the proposed unified diff to ensure it matches your architectural intent."

            parts.append(
                f"### Option {idx}: {title}\n"
                f"- **Mechanism:** {desc}\n"
                f"- **Verification:** `{verif}`\n"
                f"- **Pros:** {pros}\n"
                f"- **Trade-offs / Considerations:** {cons}\n"
            )

        parts.append("**Recommendation:** Review the unified diffs and choose the option that matches your intended code structure.")
        return InteractionResponse(status="success", message="\n".join(parts))

    @classmethod
    def _handle_apply_impact(cls, fixes: List[Dict[str, Any]], category: str) -> InteractionResponse:
        if not fixes:
            return InteractionResponse(
                status="success",
                message="No candidate fix is currently selected."
            )

        top_fix = fixes[0]
        title = top_fix.get("title", "")
        diff = top_fix.get("diff", "")
        verif = top_fix.get("verification", {})
        status = verif.get("status", "UNVERIFIED")
        checks = verif.get("checks", [])
        passed_checks = [c.get("name") for c in checks if c.get("passed")]

        msg = (
            f"**Impact of Applying '{title}':**\n\n"
            f"1. **Source Transformation:**\n"
            f"   Visual Studio Code will execute an atomic `WorkspaceEdit` on the active file buffer applying the following changes:\n"
            f"   ```diff\n{diff}\n   ```\n"
            f"2. **Pre-Computed Verification:**\n"
            f"   - Outcome: **`{status}`**\n"
            f"   - Passed checks: {', '.join(passed_checks) if passed_checks else 'None'}\n"
            f"3. **Safety Guarantee:**\n"
            f"   The extension checks the document version before applying. If you edited the file after the investigation, the edit is safely aborted to avoid conflicts.\n"
            f"4. **Action Required:**\n"
            f"   Edits are never applied automatically by messages. To execute this change, click the **⚡ Apply Correction** button above."
        )
        return InteractionResponse(status="success", message=msg)

    @classmethod
    def _handle_diff(cls, fixes: List[Dict[str, Any]]) -> InteractionResponse:
        if not fixes:
            return InteractionResponse(
                status="success",
                message="**Proposed Diff**\n\nNo candidate fix or unified diff is available for this diagnostic."
            )
        fix = fixes[0]
        diff = fix.get("diff", "")
        if not diff or not diff.strip():
            return InteractionResponse(
                status="success",
                message=f"**Proposed Diff for '{fix.get('title')}'**\n\nNo textual changes recorded."
            )
        msg = (
            f"**Proposed Source Diff for '{fix.get('title')}':**\n\n"
            f"```diff\n{diff}\n```\n\n"
            f"- **Deletions (`-`):** Lines removed or modified.\n"
            f"- **Additions (`+`):** Lines inserted or updated.\n\n"
            f"You can verify this patch using `verify` or run tests with `tests` before applying."
        )
        return InteractionResponse(status="success", message=msg)

    @classmethod
    def _handle_verify(cls, fixes: List[Dict[str, Any]], inv: Dict[str, Any]) -> InteractionResponse:
        report = inv.get("verification_report")
        if not report and fixes:
            report = fixes[0].get("verification")

        if not report:
            return InteractionResponse(
                status="success",
                message="**Verification Outcome**\n\nNo verification checks have been recorded for this diagnostic yet."
            )

        status = report.get("status", "NOT_CHECKED")
        checks = report.get("checks", [])
        limitation = report.get("limitation", "")

        parts = [
            f"**Deterministic Verification Report**\n",
            f"**Overall Status:** `{status}`\n",
            f"**Executed Checks ({len(checks)}):**\n"
        ]
        for c in checks:
            p_icon = "✓" if c.get("passed") else ("✗" if c.get("status") == "FAILED" else "○")
            parts.append(f"- {p_icon} **{c.get('name')}:** {c.get('message')} (`{c.get('status', 'PASSED' if c.get('passed') else 'FAILED')}`)")

        if limitation:
            parts.append(f"\n*Limitation:* {limitation}")

        parts.append("\n*Verification policy:* Compiler checks confirm syntax; full correctness requires running automated tests (`tests`).")
        return InteractionResponse(status="success", message="\n".join(parts))

    @classmethod
    def _handle_tests(cls, fixes: List[Dict[str, Any]], inv: Dict[str, Any]) -> InteractionResponse:
        report = inv.get("verification_report") or {}
        checks = report.get("checks", [])
        test_check = next((c for c in checks if "test" in c.get("name", "").lower()), None)

        if test_check and test_check.get("status") in ["PASSED", "FAILED"]:
            res_str = "Passed" if test_check.get("passed") else "Failed"
            msg = (
                f"**Automated Test Status: {res_str}**\n\n"
                f"- **Check:** `{test_check.get('name')}`\n"
                f"- **Outcome:** `{test_check.get('status')}`\n"
                f"- **Message:** {test_check.get('message')}\n"
            )
            if test_check.get("command"):
                msg += f"- **Executed Command:** `{test_check.get('command')}`\n"
            if test_check.get("exit_code") is not None:
                msg += f"- **Exit Code:** {test_check.get('exit_code')}\n"
            return InteractionResponse(status="success", message=msg)

        msg = (
            "**Automated Test Status: Not Checked**\n\n"
            "CompilerMate checked this proposed fix using static checks (Tokenizer, AST syntax parse, Bytecode compilation).\n\n"
            "**Why test verification matters:**\n"
            "- A change can compile with 100% valid Python syntax while still producing incorrect runtime calculations or failing test assertions.\n"
            "- Never assume a change is completely verified solely because a compiler check passes.\n"
            "- You can execute project tests independently or trigger automated test verification."
        )
        return InteractionResponse(status="success", message=msg, action="run_tests")

    @classmethod
    def _handle_history(cls, inv: Dict[str, Any]) -> InteractionResponse:
        record_id = inv.get("record_id") or inv.get("metadata", {}).get("record_id", "active-investigation")
        category = inv.get("category", "UNKNOWN")
        diag_msg = inv.get("diagnostic", {}).get("message", "")

        msg = (
            f"**Investigation Engineering Record**\n\n"
            f"- **Active Investigation ID:** `{record_id}`\n"
            f"- **Category:** `{category}`\n"
            f"- **Problem:** `{diag_msg}`\n"
            f"- **Storage:** Persisted locally in workspace `.compilermate/investigations/`.\n\n"
            f"All observed evidence, candidate diffs, verification check outputs, and decision statuses are preserved across extension sessions. "
            f"You can reopen past investigations at any time."
        )
        return InteractionResponse(status="success", message=msg, action="show_history")

    @classmethod
    def _handle_risks(cls, fixes: List[Dict[str, Any]], inv: Dict[str, Any]) -> InteractionResponse:
        risks = inv.get("unresolved_risks") or []
        if not risks and fixes:
            risks = fixes[0].get("verification", {}).get("unresolved_risks", [])

        if not risks:
            risks = [
                "Automated runtime test suite has not been executed.",
                "Semantic developer intent is unconfirmed beyond syntactic validity.",
                "Potential unverified downstream callers or variable dependencies."
            ]

        parts = [
            "**Unresolved Risks & Remaining Uncertainties:**\n",
            "The following aspects remain unverified:\n"
        ]
        for idx, r in enumerate(risks, 1):
            parts.append(f"{idx}. ⚠️ **{r}**")

        parts.append(
            "\n*Verification principle:* Do not treat a successful syntax check as proof of total correctness. "
            "Inspect the diff (`diff`) and run tests (`tests`) before committing changes."
        )
        return InteractionResponse(status="success", message="\n".join(parts))

    @classmethod
    def _handle_next_steps(cls, fixes: List[Dict[str, Any]], inv: Dict[str, Any]) -> InteractionResponse:
        verif = inv.get("verification_report") or (fixes[0].get("verification") if fixes else {})
        status = verif.get("status", "NOT_CHECKED") if isinstance(verif, dict) else "NOT_CHECKED"

        if not fixes:
            msg = (
                "**Recommended Next Steps:**\n\n"
                "1. Inspect the reported line and surrounding syntax using `evidence`.\n"
                "2. Ask `cause` to understand why the compiler flagged this line.\n"
                "3. Make manual corrections and re-run with `investigate`."
            )
        elif status == "PASSED":
            msg = (
                "**Recommended Next Steps:**\n\n"
                "1. The fix passed static checks and automated test verification.\n"
                "2. Click **Apply Fix** in the panel to apply the change.\n"
                "3. Your decision and verified diff will be recorded in the investigation history."
            )
        elif status == "PARTIALLY_VERIFIED":
            msg = (
                "**Recommended Next Steps:**\n\n"
                "1. Inspect the proposed unified diff (`diff`).\n"
                "2. Review remaining uncertainties with `risks`.\n"
                "3. Run automated tests (`tests`) to verify dynamic runtime behavior.\n"
                "4. Apply fix after review."
            )
        else:
            msg = (
                "**Recommended Next Steps:**\n\n"
                "1. Review candidate fixes with `alternatives`.\n"
                "2. Inspect the diff with `diff`.\n"
                "3. Run `verify` to inspect deterministic compiler checks."
            )
        return InteractionResponse(status="success", message=msg)

    @classmethod
    def _handle_general_query(
        cls,
        query: str,
        category: str,
        diag_msg: str,
        evidence: List[Dict[str, Any]],
        fixes: List[Dict[str, Any]],
        doc_text: str
    ) -> InteractionResponse:
        # Check if query references any evidence snippet or identifiers
        matched_tokens = []
        for ev in evidence:
            snippet = ev.get("snippet", "")
            for word in snippet.split():
                clean_word = re.sub(r"\W+", "", word)
                if len(clean_word) >= 3 and clean_word.lower() in query.lower():
                    matched_tokens.append(clean_word)

        if matched_tokens:
            msg = (
                f"You asked about `{', '.join(set(matched_tokens))}`, which is part of the code evidence identified for this `{category}` issue.\n\n"
                f"In this context, the diagnostic is: `{diag_msg}`.\n"
                f"Static analysis determined that this line cannot be compiled because it violates Python's syntactic rules for {category.lower().replace('_', ' ')}. "
                f"You can ask for clarification on the root cause (`cause`), inspect the diff (`diff`), or review verification (`verify`)."
            )
            return InteractionResponse(status="success", message=msg)

        # Fallback bounded response
        msg = (
            f"This issue is marked `{category}` (`{diag_msg}`).\n\n"
            "Try a keyword command:\n"
            "- `cause`: explain why the compiler reported this error\n"
            "- `evidence`: inspect observed facts vs inferred hypotheses\n"
            "- `trace`: follow the diagnostic through parser rules\n"
            "- `diff`: inspect proposed code modifications\n"
            "- `verify`: view deterministic multi-stage verification checks\n"
            "- `tests`: check automated test execution status\n"
            "- `risks`: review remaining uncertainties and unverified claims\n"
            "- `history`: view saved persistent investigation records\n"
            "- `next`: see the recommended next investigation action\n\n"
            "You can also ask questions in your own words (e.g. 'Why did this fail?', 'What changed?', 'What remains unverified?')."
        )
        return InteractionResponse(status="success", message=msg)
