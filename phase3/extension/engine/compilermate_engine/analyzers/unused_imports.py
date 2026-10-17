"""Analyzer for unused import diagnostics in Python."""
from __future__ import annotations
import ast
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

UNUSED_IMPORT_PATTERNS = [
    re.compile(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s+is not accessed", re.IGNORECASE),
    re.compile(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s+imported but unused", re.IGNORECASE),
    re.compile(r"imported but unused:\s+['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", re.IGNORECASE),
    re.compile(r"unused import\s+['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", re.IGNORECASE),
]

class UnusedImportAnalyzer:
    """Investigates unused import diagnostics (Pylance reportUnusedImport, Flake8 F401)."""

    @classmethod
    def can_handle(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> bool:
        code_str = str(diagnostic.code).lower()
        if "reportunusedimport" in code_str or "f401" in code_str:
            return True
        msg = diagnostic.message.lower()
        return "is not accessed" in msg or "imported but unused" in msg or "unused import" in msg

    @classmethod
    def _extract_unused_name(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> Optional[str]:
        for p in UNUSED_IMPORT_PATTERNS:
            m = p.search(diagnostic.message)
            if m:
                return m.group(1)

        # Fallback to diagnostic range
        lines = document.text.splitlines()
        r = diagnostic.range
        if 0 <= r.start.line < len(lines):
            line_str = lines[r.start.line]
            candidate = line_str[r.start.character:r.end.character].strip()
            if candidate and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", candidate):
                return candidate
        return None

    @classmethod
    def analyze(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> Optional[InvestigationResult]:
        unused_name = cls._extract_unused_name(diagnostic, document)
        lines = document.text.splitlines(keepends=True)
        diag_line_0 = diagnostic.range.start.line
        diag_line_1 = diag_line_0 + 1

        if diag_line_0 >= len(lines):
            return None

        line_raw = lines[diag_line_0]
        line_stripped = line_raw.strip()

        # Must be an import line
        if not (line_stripped.startswith("import ") or line_stripped.startswith("from ")):
            return None

        if not unused_name:
            # Try finding imported name in the line
            m = re.search(r"\b(?:import|from\s+[\w\.]+\s+import)\s+([\w,\s]+)", line_stripped)
            if m:
                names = [n.strip() for n in m.group(1).split(',')]
                if len(names) == 1:
                    unused_name = names[0].split()[0]

        if not unused_name:
            return None

        evidence = [
            EvidenceItem(
                title=f"Unused import statement for '{unused_name}'",
                line=diag_line_1,
                column=diagnostic.range.start.character + 1,
                snippet=line_raw.strip(),
                annotation=f"'{unused_name}' is imported here but never referenced elsewhere in this file."
            )
        ]

        candidate_fixes: List[CandidateFix] = []

        # Determine edit: remove entire line if single import, or remove name from comma list
        # Check if line contains other imported names
        from_match = re.match(r"^(\s*from\s+[\w\.]+\s+import\s+)(.+)$", line_raw.rstrip('\r\n'))
        import_match = re.match(r"^(\s*import\s+)(.+)$", line_raw.rstrip('\r\n'))

        if from_match:
            prefix, names_part = from_match.groups()
            names = [n.strip() for n in names_part.split(',')]
            # Check if matching unused_name
            matching = [n for n in names if n == unused_name or n.startswith(f"{unused_name} as ")]
            if len(names) > 1 and matching:
                # Remove just this name from the comma-separated list
                remaining_names = [n for n in names if n not in matching]
                new_line = f"{prefix}{', '.join(remaining_names)}\n"
                edit = [
                    SourceEdit(
                        range=Range(
                            start=Position(line=diag_line_0, character=0),
                            end=Position(line=diag_line_0, character=len(line_raw))
                        ),
                        new_text=new_line
                    )
                ]
                v_edit, p_edit = FixVerifier.verify(document.text, edit, diagnostic.message)
                candidate_fixes.append(CandidateFix(
                    id=f"fix-remove-import-name-{unused_name}",
                    title=f"Remove '{unused_name}' from import list on line {diag_line_1}",
                    description=f"Removes '{unused_name}' while preserving the remaining imports ({', '.join(remaining_names)}).",
                    edits=edit,
                    verification=v_edit,
                    diff=FixVerifier.generate_diff(document.text, p_edit)
                ))
            else:
                # Delete the entire line
                edit = [
                    SourceEdit(
                        range=Range(
                            start=Position(line=diag_line_0, character=0),
                            end=Position(line=diag_line_0 + 1, character=0) if diag_line_0 + 1 < len(lines) else Position(line=diag_line_0, character=len(line_raw))
                        ),
                        new_text=""
                    )
                ]
                v_edit, p_edit = FixVerifier.verify(document.text, edit, diagnostic.message)
                candidate_fixes.append(CandidateFix(
                    id=f"fix-delete-unused-import-line-{diag_line_1}",
                    title=f"Delete unused import line {diag_line_1}",
                    description=f"Removes the entire unused import statement 'from ... import {unused_name}'.",
                    edits=edit,
                    verification=v_edit,
                    diff=FixVerifier.generate_diff(document.text, p_edit)
                ))
        elif import_match:
            prefix, names_part = import_match.groups()
            names = [n.strip() for n in names_part.split(',')]
            matching = [n for n in names if n == unused_name or n.startswith(f"{unused_name} as ")]
            if len(names) > 1 and matching:
                remaining_names = [n for n in names if n not in matching]
                new_line = f"{prefix}{', '.join(remaining_names)}\n"
                edit = [
                    SourceEdit(
                        range=Range(
                            start=Position(line=diag_line_0, character=0),
                            end=Position(line=diag_line_0, character=len(line_raw))
                        ),
                        new_text=new_line
                    )
                ]
                v_edit, p_edit = FixVerifier.verify(document.text, edit, diagnostic.message)
                candidate_fixes.append(CandidateFix(
                    id=f"fix-remove-import-module-{unused_name}",
                    title=f"Remove '{unused_name}' from import statement on line {diag_line_1}",
                    description=f"Removes '{unused_name}' from the import list on line {diag_line_1}.",
                    edits=edit,
                    verification=v_edit,
                    diff=FixVerifier.generate_diff(document.text, p_edit)
                ))
            else:
                edit = [
                    SourceEdit(
                        range=Range(
                            start=Position(line=diag_line_0, character=0),
                            end=Position(line=diag_line_0 + 1, character=0) if diag_line_0 + 1 < len(lines) else Position(line=diag_line_0, character=len(line_raw))
                        ),
                        new_text=""
                    )
                ]
                v_edit, p_edit = FixVerifier.verify(document.text, edit, diagnostic.message)
                candidate_fixes.append(CandidateFix(
                    id=f"fix-delete-unused-import-line-{diag_line_1}",
                    title=f"Delete unused import line {diag_line_1}",
                    description=f"Removes the unused import '{line_stripped}'.",
                    edits=edit,
                    verification=v_edit,
                    diff=FixVerifier.generate_diff(document.text, p_edit)
                ))

        explanation = Explanation(
            summary=f"Unused import: '{unused_name}' is imported but not referenced.",
            details=(
                f"Importing '{unused_name}' brings it into the module namespace, but no subsequent code references it. "
                f"Unused imports increase module loading time, clutter the namespace, and indicate potentially dead code."
            ),
            cause_vs_symptom=f"The import statement on line {diag_line_1} is not utilized in the document.",
            next_steps=f"Remove '{unused_name}' from the import statement or use it in the implementation."
        )

        return InvestigationResult(
            status="success",
            category="UNUSED_IMPORT",
            diagnostic=diagnostic,
            explanation=explanation,
            evidence=evidence,
            candidate_fixes=candidate_fixes,
            metadata={"unused_name": unused_name, "line": diag_line_1}
        )
