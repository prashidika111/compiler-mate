"""Command-line interface and IPC handler for CompilerMate Phase 3 engine."""
from __future__ import annotations
import argparse
import json
import sys
from typing import Dict, Any
import datetime
from .models import (
    InvestigationRequest,
    InteractionRequest,
    DiagnosticInput,
    DocumentInput,
    Range,
    Position,
    InvestigationResult,
    InteractionResponse,
    SourceEdit,
    VerificationReport,
    asdict
)
from .investigator import DiagnosticInvestigator
from .conversation import ConversationEngine
from .verifier import FixVerifier

def run_stdin_ipc() -> int:
    """Read a JSON request (investigate, interact, or verify) from stdin and write the result to stdout."""
    raw_input = sys.stdin.read()
    if not raw_input.strip():
        err_res = {
            "status": "error",
            "category": "INVALID_REQUEST",
            "error_message": "Empty payload received on stdin."
        }
        sys.stdout.write(json.dumps(err_res, indent=2) + "\n")
        return 1

    try:
        data = json.loads(raw_input)
    except json.JSONDecodeError as jde:
        err_res = {
            "status": "error",
            "category": "INVALID_JSON",
            "error_message": f"Malformed JSON input: {jde}"
        }
        sys.stdout.write(json.dumps(err_res, indent=2) + "\n")
        return 1

    try:
        command = data.get("command", "investigate")
        if command == "interact":
            req_int = InteractionRequest.from_dict(data)
            int_res = ConversationEngine.respond(req_int)
            sys.stdout.write(json.dumps(int_res.to_dict(), indent=2) + "\n")
            return 0
        elif command == "verify":
            doc_data = data.get("document", {})
            text = doc_data.get("text", "")
            raw_edits = data.get("edits", [])
            edits = [SourceEdit.from_dict(e) for e in raw_edits] if isinstance(raw_edits, list) else []
            diag_data = data.get("diagnostic", {})
            diag_msg = diag_data.get("message", "")
            diag_line_1 = diag_data.get("range", {}).get("start", {}).get("line", 0) + 1
            run_tests = bool(data.get("run_tests", False))
            test_command = data.get("test_command")
            cwd = data.get("cwd")

            verif_result, patched_text = FixVerifier.verify(
                original_text=text,
                edits=edits,
                original_diagnostic_message=diag_msg,
                test_command=test_command,
                cwd=cwd,
                run_tests=run_tests
            )
            resolved, remaining, new_errs = FixVerifier.compare_diagnostics(
                original_text=text,
                patched_text=patched_text,
                original_diagnostic_line_1=diag_line_1
            )
            diff = FixVerifier.generate_diff(text, patched_text)

            report = VerificationReport(
                status=verif_result.status,
                checks=verif_result.checks,
                initial_diagnostics=[DiagnosticInput.from_dict(diag_data)] if diag_data else [],
                remaining_diagnostics=[DiagnosticInput(message=r, range=Range(start=Position(0,0), end=Position(0,0))) for r in remaining],
                new_diagnostics=[DiagnosticInput(message=n, range=Range(start=Position(0,0), end=Position(0,0))) for n in new_errs],
                unresolved_risks=list(verif_result.unresolved_risks),
                limitation=verif_result.limitation,
                summary=f"Verification status: {verif_result.status}. {verif_result.limitation}",
                timestamp=datetime.datetime.now().isoformat()
            )
            out_data = {
                "status": "success",
                "verification_report": asdict(report),
                "diff": diff,
                "patched_text": patched_text
            }
            sys.stdout.write(json.dumps(out_data, indent=2) + "\n")
            return 0
        else:
            req = InvestigationRequest.from_dict(data)
            result = DiagnosticInvestigator.investigate(req)
            sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
            return 0
    except Exception as e:
        err_res = {
            "status": "error",
            "category": "INTERNAL_EXCEPTION",
            "error_message": f"Engine exception during execution: {e}"
        }
        sys.stdout.write(json.dumps(err_res, indent=2) + "\n")
        return 1

def main():
    parser = argparse.ArgumentParser(description="CompilerMate Python Diagnostic Investigation Engine")
    subparsers = parser.add_subparsers(dest="subcommand")

    # Subcommand: investigate (default when piped via stdin)
    inv_parser = subparsers.add_parser("investigate", help="Investigate a diagnostic")
    inv_parser.add_argument("--json", action="store_true", help="Read JSON request from stdin")
    inv_parser.add_argument("--file", type=str, help="Path to Python file for direct CLI test")
    inv_parser.add_argument("--line", type=int, default=1, help="1-based diagnostic line")
    inv_parser.add_argument("--col", type=int, default=1, help="1-based diagnostic column")
    inv_parser.add_argument("--message", type=str, default="SyntaxError: invalid syntax", help="Diagnostic error message")

    # Subcommand: interact (two-way interaction over stdin)
    int_parser = subparsers.add_parser("interact", help="Interact with CompilerMate")
    int_parser.add_argument("--json", action="store_true", help="Read JSON interaction request from stdin")

    # Subcommand: verify (multi-stage verification over stdin)
    verif_parser = subparsers.add_parser("verify", help="Verify candidate fix")
    verif_parser.add_argument("--json", action="store_true", help="Read JSON verification request from stdin")

    args = parser.parse_args()

    if args.subcommand == "investigate" and args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
        line_0 = max(0, args.line - 1)
        col_0 = max(0, args.col - 1)
        req = InvestigationRequest(
            command="investigate",
            document=DocumentInput(uri=f"file:///{args.file}", text=text),
            diagnostic=DiagnosticInput(
                message=args.message,
                range=Range(start=Position(line=line_0, character=col_0), end=Position(line=line_0, character=col_0 + 1))
            )
        )
        res = DiagnosticInvestigator.investigate(req)
        print(json.dumps(res.to_dict(), indent=2))
        sys.exit(0)
    else:
        # Default IPC over stdin
        sys.exit(run_stdin_ipc())

if __name__ == "__main__":
    main()
