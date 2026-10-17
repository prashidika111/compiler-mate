from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Union, Dict, Any

@dataclass
class Position:
    """0-based line and character position matching VS Code LSP coordinates."""
    line: int
    character: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Position:
        return cls(line=int(data.get("line", 0)), character=int(data.get("character", 0)))

@dataclass
class Range:
    """0-based text range matching VS Code LSP coordinates."""
    start: Position
    end: Position

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Range:
        return cls(
            start=Position.from_dict(data.get("start", {})),
            end=Position.from_dict(data.get("end", {}))
        )

@dataclass
class DiagnosticInput:
    """Diagnostic information received from VS Code."""
    message: str
    range: Range
    code: Optional[Union[str, int]] = None
    source: Optional[str] = None
    severity: int = 1  # 1 = Error, 2 = Warning, 3 = Info, 4 = Hint

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DiagnosticInput:
        return cls(
            message=str(data.get("message", "")),
            range=Range.from_dict(data.get("range", {})),
            code=data.get("code"),
            source=data.get("source"),
            severity=int(data.get("severity", 1)),
        )

@dataclass
class DocumentInput:
    """In-memory document context received from VS Code."""
    uri: str
    text: str
    language_id: str = "python"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DocumentInput:
        return cls(
            uri=str(data.get("uri", "")),
            text=str(data.get("text", "")),
            language_id=str(data.get("languageId", data.get("language_id", "python")))
        )

@dataclass
class InvestigationRequest:
    command: str
    document: DocumentInput
    diagnostic: DiagnosticInput

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InvestigationRequest:
        return cls(
            command=str(data.get("command", "investigate")),
            document=DocumentInput.from_dict(data.get("document", {})),
            diagnostic=DiagnosticInput.from_dict(data.get("diagnostic", {}))
        )

@dataclass
class EvidenceItem:
    """Concrete evidence gathered from the source code.
    kind must be one of:
      - 'OBSERVED': directly available in diagnostics, source code, or tool output
      - 'INFERRED': plausible explanation or hypothesis derived from evidence
      - 'UNVERIFIED': claims requiring further investigation or runtime checks
    """
    title: str
    line: int        # 1-based for human presentation
    column: int      # 1-based for human presentation
    snippet: str
    annotation: str
    kind: str = "OBSERVED"  # "OBSERVED", "INFERRED", "UNVERIFIED"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvidenceItem:
        return cls(
            title=str(data.get("title", "")),
            line=int(data.get("line", 1)),
            column=int(data.get("column", 1)),
            snippet=str(data.get("snippet", "")),
            annotation=str(data.get("annotation", "")),
            kind=str(data.get("kind", "OBSERVED")),
        )

@dataclass
class SourceEdit:
    """Precise source modification formatted for VS Code WorkspaceEdit."""
    range: Range
    new_text: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SourceEdit:
        return cls(
            range=Range.from_dict(data.get("range", {})),
            new_text=str(data.get("new_text", data.get("newText", "")))
        )

@dataclass
class VerificationCheck:
    """Individual verification check performed on a candidate fix."""
    name: str
    passed: bool
    message: str
    status: str = "PASSED"  # "PASSED", "FAILED", "NOT_CHECKED", "UNABLE_TO_VERIFY"
    command: Optional[str] = None
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    duration_ms: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VerificationCheck:
        return cls(
            name=str(data.get("name", "")),
            passed=bool(data.get("passed", False)),
            message=str(data.get("message", "")),
            status=str(data.get("status", "PASSED" if data.get("passed") else "FAILED")),
            command=data.get("command"),
            exit_code=data.get("exit_code"),
            stdout=data.get("stdout"),
            stderr=data.get("stderr"),
            duration_ms=data.get("duration_ms"),
        )

@dataclass
class VerificationResult:
    """Comprehensive verification outcome for a candidate fix.
    Statuses include: "PASSED", "FAILED", "PARTIALLY_VERIFIED", "NOT_CHECKED", "UNABLE_TO_VERIFY"
    (legacy: "VERIFIED", "INCONCLUSIVE").
    """
    status: str       # "PASSED", "FAILED", "PARTIALLY_VERIFIED", "VERIFIED", "NOT_CHECKED", "UNABLE_TO_VERIFY"
    checks: List[VerificationCheck] = field(default_factory=list)
    limitation: str = ""
    unresolved_risks: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VerificationResult:
        raw_checks = data.get("checks", [])
        return cls(
            status=str(data.get("status", "NOT_CHECKED")),
            checks=[VerificationCheck.from_dict(c) for c in raw_checks] if isinstance(raw_checks, list) else [],
            limitation=str(data.get("limitation", "")),
            unresolved_risks=list(data.get("unresolved_risks", []))
        )

@dataclass
class VerificationReport:
    """Consolidated before-and-after deterministic verification report."""
    status: str  # "NOT_CHECKED", "IN_PROGRESS", "PASSED", "FAILED", "PARTIALLY_VERIFIED", "UNABLE_TO_VERIFY"
    checks: List[VerificationCheck] = field(default_factory=list)
    initial_diagnostics: List[DiagnosticInput] = field(default_factory=list)
    remaining_diagnostics: List[DiagnosticInput] = field(default_factory=list)
    new_diagnostics: List[DiagnosticInput] = field(default_factory=list)
    unresolved_risks: List[str] = field(default_factory=list)
    limitation: str = ""
    summary: str = ""
    timestamp: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VerificationReport:
        return cls(
            status=str(data.get("status", "NOT_CHECKED")),
            checks=[VerificationCheck.from_dict(c) for c in data.get("checks", [])],
            initial_diagnostics=[DiagnosticInput.from_dict(d) for d in data.get("initial_diagnostics", [])],
            remaining_diagnostics=[DiagnosticInput.from_dict(d) for d in data.get("remaining_diagnostics", [])],
            new_diagnostics=[DiagnosticInput.from_dict(d) for d in data.get("new_diagnostics", [])],
            unresolved_risks=list(data.get("unresolved_risks", [])),
            limitation=str(data.get("limitation", "")),
            summary=str(data.get("summary", "")),
            timestamp=data.get("timestamp"),
        )

@dataclass
class CandidateFix:
    """A deterministic, evidence-backed candidate correction."""
    id: str
    title: str
    description: str
    edits: List[SourceEdit]
    verification: VerificationResult
    diff: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CandidateFix:
        raw_edits = data.get("edits", [])
        raw_verif = data.get("verification", {})
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            edits=[SourceEdit.from_dict(e) for e in raw_edits] if isinstance(raw_edits, list) else [],
            verification=VerificationResult.from_dict(raw_verif) if isinstance(raw_verif, dict) else raw_verif,
            diff=data.get("diff")
        )

@dataclass
class Explanation:
    """Plain-language explanation backed by code evidence."""
    summary: str
    details: str
    cause_vs_symptom: Optional[str] = None
    next_steps: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Explanation:
        return cls(
            summary=str(data.get("summary", "")),
            details=str(data.get("details", "")),
            cause_vs_symptom=data.get("cause_vs_symptom"),
            next_steps=str(data.get("next_steps", ""))
        )

@dataclass
class InvestigationRecord:
    """Persistent engineering record preserving context, evidence, decisions, and checks."""
    id: str
    created_at: str
    updated_at: str
    status: str                     # "OPEN", "VERIFIED", "PARTIALLY_VERIFIED", "FAILED", "APPLIED", "REJECTED", "CLOSED"
    document_uri: str
    document_version: Optional[int] = None
    source_hash: str = ""
    source_excerpt: str = ""
    diagnostic: DiagnosticInput = field(default_factory=lambda: DiagnosticInput(message="", range=Range(start=Position(0,0), end=Position(0,0))))
    problem_description: str = ""
    category: str = "UNKNOWN"
    explanation: Optional[Explanation] = None
    evidence: List[EvidenceItem] = field(default_factory=list)
    candidate_fixes: List[CandidateFix] = field(default_factory=list)
    selected_fix_id: Optional[str] = None
    verification_report: Optional[VerificationReport] = None
    decision_status: str = "PENDING"  # "PENDING", "ACCEPTED", "REJECTED", "APPLIED"
    applied_diff: Optional[str] = None
    unresolved_risks: List[str] = field(default_factory=list)
    history: List[ChatMessage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InvestigationRecord:
        raw_ev = data.get("evidence", [])
        raw_fixes = data.get("candidate_fixes", [])
        raw_hist = data.get("history", [])
        raw_report = data.get("verification_report")
        raw_expl = data.get("explanation")
        return cls(
            id=str(data.get("id", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            status=str(data.get("status", "OPEN")),
            document_uri=str(data.get("document_uri", "")),
            document_version=data.get("document_version"),
            source_hash=str(data.get("source_hash", "")),
            source_excerpt=str(data.get("source_excerpt", "")),
            diagnostic=DiagnosticInput.from_dict(data.get("diagnostic", {})),
            problem_description=str(data.get("problem_description", "")),
            category=str(data.get("category", "UNKNOWN")),
            explanation=Explanation.from_dict(raw_expl) if raw_expl else None,
            evidence=[EvidenceItem.from_dict(e) for e in raw_ev] if isinstance(raw_ev, list) else [],
            candidate_fixes=[CandidateFix.from_dict(f) for f in raw_fixes] if isinstance(raw_fixes, list) else [],
            selected_fix_id=data.get("selected_fix_id"),
            verification_report=VerificationReport.from_dict(raw_report) if raw_report else None,
            decision_status=str(data.get("decision_status", "PENDING")),
            applied_diff=data.get("applied_diff"),
            unresolved_risks=list(data.get("unresolved_risks", [])),
            history=[ChatMessage.from_dict(m) for m in raw_hist] if isinstance(raw_hist, list) else [],
            metadata=dict(data.get("metadata", {}))
        )

@dataclass
class InvestigationResult:
    """Complete investigation result sent back to VS Code."""
    status: str               # "success", "unsupported", "error"
    category: str             # e.g., "UNCLOSED_DELIMITER", "MISSING_COLON", "UNDEFINED_NAME"
    diagnostic: DiagnosticInput
    explanation: Optional[Explanation] = None
    evidence: List[EvidenceItem] = field(default_factory=list)
    candidate_fixes: List[CandidateFix] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    record_id: Optional[str] = None
    verification_report: Optional[VerificationReport] = None
    unresolved_risks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to clean JSON-serializable dictionary."""
        return asdict(self)

@dataclass
class ChatMessage:
    """Individual message in a multi-turn two-way investigation conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChatMessage:
        return cls(
            role=str(data.get("role", "user")),
            content=str(data.get("content", "")),
            timestamp=data.get("timestamp")
        )

@dataclass
class InteractionRequest:
    """Request payload for two-way conversation with CompilerMate."""
    command: str
    document: DocumentInput
    diagnostic: DiagnosticInput
    investigation_result: Dict[str, Any]
    user_message: str
    history: List[ChatMessage] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InteractionRequest:
        raw_history = data.get("history", [])
        history_objs = [ChatMessage.from_dict(m) for m in raw_history] if isinstance(raw_history, list) else []
        return cls(
            command=str(data.get("command", "interact")),
            document=DocumentInput.from_dict(data.get("document", {})),
            diagnostic=DiagnosticInput.from_dict(data.get("diagnostic", {})),
            investigation_result=data.get("investigation_result", {}),
            user_message=str(data.get("user_message", "")),
            history=history_objs
        )

@dataclass
class InteractionResponse:
    """Response returned from a two-way conversational interaction turn."""
    status: str       # "success" or "error"
    message: str      # Conversational response text
    action: str = "none"   # "none", "select_fix", "reinvestigate"
    selected_fix_id: Optional[str] = None
    candidate_fixes: Optional[List[CandidateFix]] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
