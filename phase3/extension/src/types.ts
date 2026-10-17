/**
 * Type definitions for CompilerMate Phase 3 VS Code extension and Python engine IPC.
 */

export interface Position {
  line: number;      // 0-based line
  character: number; // 0-based character
}

export interface Range {
  start: Position;
  end: Position;
}

export interface DiagnosticInput {
  message: string;
  range: Range;
  code?: string | number | null;
  source?: string | null;
  severity: number;  // 1 = Error, 2 = Warning, 3 = Info, 4 = Hint
}

export interface DocumentInput {
  uri: string;
  text: string;
  language_id: string;
}

export interface InvestigationRequest {
  command: string;
  document: DocumentInput;
  diagnostic: DiagnosticInput;
}

export type EvidenceKind = "OBSERVED" | "INFERRED" | "UNVERIFIED";

export interface EvidenceItem {
  title: string;
  line: number;      // 1-based line for display
  column: number;    // 1-based column for display
  snippet: string;
  annotation: string;
  kind?: EvidenceKind;
}

export interface SourceEdit {
  range: Range;
  new_text: string;
}

export type VerificationStatus =
  | "NOT_CHECKED"
  | "IN_PROGRESS"
  | "PASSED"
  | "FAILED"
  | "PARTIALLY_VERIFIED"
  | "UNABLE_TO_VERIFY"
  | "VERIFIED"       // backward compatible
  | "INCONCLUSIVE";  // backward compatible

export interface VerificationCheck {
  name: string;
  passed: boolean;
  message: string;
  status?: VerificationStatus;
  command?: string | null;
  exit_code?: number | null;
  stdout?: string | null;
  stderr?: string | null;
  duration_ms?: number | null;
}

export interface VerificationResult {
  status: VerificationStatus;
  checks: VerificationCheck[];
  limitation: string;
  unresolved_risks?: string[];
}

export interface VerificationReport {
  status: VerificationStatus;
  checks: VerificationCheck[];
  initial_diagnostics?: DiagnosticInput[];
  remaining_diagnostics?: DiagnosticInput[];
  new_diagnostics?: DiagnosticInput[];
  unresolved_risks: string[];
  limitation: string;
  summary: string;
  timestamp?: string | null;
}

export interface CandidateFix {
  id: string;
  title: string;
  description: string;
  edits: SourceEdit[];
  verification: VerificationResult;
  diff?: string | null;
}

export interface Explanation {
  summary: string;
  details: string;
  cause_vs_symptom?: string | null;
  next_steps?: string;
}

export interface InvestigationRecord {
  id: string;
  created_at: string;
  updated_at: string;
  status: "OPEN" | "VERIFIED" | "PARTIALLY_VERIFIED" | "FAILED" | "APPLIED" | "REJECTED" | "CLOSED";
  document_uri: string;
  document_version?: number | null;
  source_hash: string;
  source_excerpt: string;
  diagnostic: DiagnosticInput;
  problem_description: string;
  category: string;
  explanation?: Explanation | null;
  evidence: EvidenceItem[];
  candidate_fixes: CandidateFix[];
  selected_fix_id?: string | null;
  verification_report?: VerificationReport | null;
  decision_status: "PENDING" | "ACCEPTED" | "REJECTED" | "APPLIED";
  applied_diff?: string | null;
  unresolved_risks: string[];
  history: ChatMessage[];
  metadata: Record<string, any>;
}

export interface InvestigationIndexEntry {
  id: string;
  created_at: string;
  updated_at: string;
  status: string;
  document_uri: string;
  document_name: string;
  category: string;
  problem_description: string;
  decision_status: string;
  has_diff: boolean;
  verification_status?: string;
}

export interface InvestigationResult {
  status: "success" | "unsupported" | "error";
  category: string;
  diagnostic: DiagnosticInput;
  explanation?: Explanation | null;
  evidence: EvidenceItem[];
  candidate_fixes: CandidateFix[];
  metadata: Record<string, any>;
  error_message?: string | null;
  record_id?: string | null;
  verification_report?: VerificationReport | null;
  unresolved_risks?: string[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string | null;
}

export interface InteractionRequest {
  command: "interact";
  document: DocumentInput;
  diagnostic: DiagnosticInput;
  investigation_result: InvestigationResult | Record<string, any>;
  user_message: string;
  history: ChatMessage[];
  active_record?: InvestigationRecord | null;
}

export interface InteractionResponse {
  status: "success" | "error";
  message: string;
  action?: "none" | "select_fix" | "reinvestigate" | "show_history" | "reopen_record" | "apply_fix" | "run_tests";
  selected_fix_id?: string | null;
  target_record_id?: string | null;
  candidate_fixes?: CandidateFix[] | null;
  verification_report?: VerificationReport | null;
  unresolved_risks?: string[] | null;
  error_message?: string | null;
}

export interface VerificationIPCRequest {
  command: "verify";
  document: DocumentInput;
  diagnostic: DiagnosticInput;
  edits: SourceEdit[];
  run_tests?: boolean;
  test_command?: string;
  cwd?: string;
}

export interface VerificationIPCResponse {
  status: "success" | "error";
  verification_report?: VerificationReport;
  diff?: string;
  patched_text?: string;
  category?: string;
  error_message?: string;
}
