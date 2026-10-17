"""Master investigator module for CompilerMate Phase 3."""
from __future__ import annotations
import datetime
import hashlib
import logging
from typing import Optional, List, Type
from .models import (
    DiagnosticInput,
    DocumentInput,
    InvestigationRequest,
    InvestigationResult,
    Explanation,
    EvidenceItem,
    VerificationReport
)
from .analyzers import (
    DelimiterAnalyzer,
    MissingColonAnalyzer,
    IndentationAnalyzer,
    UnterminatedStringAnalyzer,
    UndefinedNameAnalyzer,
    UnusedImportAnalyzer,
)

ANALYZERS = [
    DelimiterAnalyzer,
    MissingColonAnalyzer,
    IndentationAnalyzer,
    UnterminatedStringAnalyzer,
    UndefinedNameAnalyzer,
    UnusedImportAnalyzer,
]

logger = logging.getLogger(__name__)


class DiagnosticInvestigator:
    """Dispatches diagnostic requests to appropriate category analyzers."""

    @classmethod
    def investigate(cls, request: InvestigationRequest) -> InvestigationResult:
        doc = request.document
        diag = request.diagnostic

        # Each backend analyzer is a deterministic rule set. Preserve the rule identity
        # and source snapshot so follow-up turns can reject stale conclusions.
        source_hash = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
        analyzer_failures = []
        for analyzer_cls in ANALYZERS:
            try:
                if analyzer_cls.can_handle(diag, doc):
                    result = analyzer_cls.analyze(diag, doc)
                    if result is not None:
                        result.metadata.update({
                            "analyzer": analyzer_cls.__name__,
                            "analysis_backend": "python_diagnostic_rules",
                            "source_sha256": source_hash,
                            "rule_based": True,
                        })
                        return cls._finalize_result(result, doc, diag, source_hash)
            except Exception as exc:
                # A failed rule must not be silently presented as an unsupported
                # diagnostic; record it for debugging and make the limitation visible.
                logger.exception("Analyzer %s failed", analyzer_cls.__name__)
                analyzer_failures.append({"analyzer": analyzer_cls.__name__, "error": str(exc)})

        result = cls._create_unsupported_result(diag, doc)
        result.metadata.update({
            "analysis_backend": "python_diagnostic_rules",
            "source_sha256": source_hash,
            "rule_based": True,
        })
        if analyzer_failures:
            result.status = "error"
            result.category = "ANALYZER_FAILURE"
            result.metadata["analyzer_failures"] = analyzer_failures
            result.error_message = "One or more diagnostic rules failed; this result is not a clean unsupported-category determination."
            if result.explanation:
                result.explanation.details += " At least one applicable analyzer failed internally, so this result may be incomplete."
        return cls._finalize_result(result, doc, diag, source_hash)

    @classmethod
    def _finalize_result(cls, result: InvestigationResult, doc: DocumentInput, diag: DiagnosticInput, source_hash: str) -> InvestigationResult:
        record_seed = f"{doc.uri}:{diag.range.start.line}:{diag.message}:{source_hash[:8]}"
        record_id = f"inv-{hashlib.sha256(record_seed.encode('utf-8')).hexdigest()[:12]}"
        result.record_id = record_id
        result.metadata["record_id"] = record_id
        result.metadata["timestamp"] = datetime.datetime.now().isoformat()

        if result.candidate_fixes:
            for fix in result.candidate_fixes:
                if fix.verification and fix.verification.unresolved_risks:
                    for r in fix.verification.unresolved_risks:
                        if r not in result.unresolved_risks:
                            result.unresolved_risks.append(r)
        else:
            if result.status == "unsupported":
                result.unresolved_risks.append("Issue category is outside deterministic automated repair capabilities.")

        if result.candidate_fixes and result.candidate_fixes[0].verification:
            primary_v = result.candidate_fixes[0].verification
            result.verification_report = VerificationReport(
                status=primary_v.status,
                checks=primary_v.checks,
                initial_diagnostics=[diag],
                remaining_diagnostics=[],
                new_diagnostics=[],
                unresolved_risks=list(result.unresolved_risks),
                limitation=primary_v.limitation,
                summary=f"Candidate fix status: {primary_v.status}. {primary_v.limitation}",
                timestamp=datetime.datetime.now().isoformat()
            )
        return result

    @classmethod
    def _create_unsupported_result(cls, diag: DiagnosticInput, doc: DocumentInput) -> InvestigationResult:
        diag_line_0 = diag.range.start.line
        diag_line_1 = diag_line_0 + 1
        lines = doc.text.splitlines()
        snippet = lines[diag_line_0].strip() if 0 <= diag_line_0 < len(lines) else ""

        evidence = []
        if snippet:
            evidence.append(EvidenceItem(
                title="Reported diagnostic location",
                line=diag_line_1,
                column=diag.range.start.character + 1,
                snippet=snippet,
                annotation=f"Reported issue: {diag.message}"
            ))

        explanation = Explanation(
            summary=f"Diagnostic: {diag.message}",
            details=(
                f"CompilerMate inspected the source around line {diag_line_1}. "
                f"This diagnostic is currently outside the supported deterministic repair categories "
                f"(such as unclosed delimiters, missing colons, indentation errors, unterminated strings, "
                f"undefined variable typos, and unused imports). No safe deterministic fix was generated."
            ),
            cause_vs_symptom="No deterministic root cause could be proven with current static rules.",
            next_steps="Review the diagnostic message and inspect the surrounding syntax manually."
        )

        return InvestigationResult(
            status="unsupported",
            category="UNSUPPORTED",
            diagnostic=diag,
            explanation=explanation,
            evidence=evidence,
            candidate_fixes=[],
            metadata={"supported_categories": [a.__name__ for a in ANALYZERS]}
        )
