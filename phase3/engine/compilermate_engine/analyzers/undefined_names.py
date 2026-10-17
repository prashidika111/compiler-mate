"""Analyzer for undefined names and typographical error diagnostics."""
from __future__ import annotations
import ast
import builtins
import difflib
import re
from typing import Optional, List, Set, Dict, Tuple
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

COMMON_STDLIB_MODULES = {
    "math", "sys", "os", "json", "re", "datetime", "random", "time",
    "collections", "itertools", "functools", "typing", "pathlib",
    "subprocess", "shutil", "copy", "io", "string", "tempfile"
}

BUILTIN_NAMES = set(dir(builtins))

UNDEFINED_PATTERNS = [
    re.compile(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s+is not defined", re.IGNORECASE),
    re.compile(r"name\s+['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s+is not defined", re.IGNORECASE),
    re.compile(r"undefined name\s+['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", re.IGNORECASE),
    re.compile(r"cannot access attribute ['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", re.IGNORECASE),
]

class SymbolCollector(ast.NodeVisitor):
    """Collects all defined symbols, functions, classes, and imports in a Python AST."""

    def __init__(self):
        self.definitions: Dict[str, List[Tuple[int, int]]] = {}  # name -> [(line_1, col_0)]

    def _add(self, name: str, line: int, col: int):
        if name not in self.definitions:
            self.definitions[name] = []
        self.definitions[name].append((line, col))

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._add(node.name, node.lineno, node.col_offset)
        for arg in node.args.args:
            self._add(arg.arg, arg.lineno, arg.col_offset)
        for arg in node.args.posonlyargs:
            self._add(arg.arg, arg.lineno, arg.col_offset)
        for arg in node.args.kwonlyargs:
            self._add(arg.arg, arg.lineno, arg.col_offset)
        if node.args.vararg:
            self._add(node.args.vararg.arg, node.args.vararg.lineno, node.args.vararg.col_offset)
        if node.args.kwarg:
            self._add(node.args.kwarg.arg, node.args.kwarg.lineno, node.args.kwarg.col_offset)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)  # type: ignore

    def visit_ClassDef(self, node: ast.ClassDef):
        self._add(node.name, node.lineno, node.col_offset)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Store):
            self._add(node.id, node.lineno, node.col_offset)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name
            self._add(name, node.lineno, node.col_offset)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            name = alias.asname or alias.name
            self._add(name, node.lineno, node.col_offset)
        self.generic_visit(node)

class UndefinedNameAnalyzer:
    """Investigates undefined name diagnostics and checks for plausible typographical errors
    or missing standard library imports.
    """

    @classmethod
    def can_handle(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> bool:
        msg = diagnostic.message.lower()
        if "not defined" in msg or "undefined name" in msg or "reportundefinedvariable" in str(diagnostic.code).lower():
            return True
        return False

    @classmethod
    def _extract_name(cls, diagnostic: DiagnosticInput, document: DocumentInput) -> Optional[str]:
        # 1. Match from diagnostic message
        for pattern in UNDEFINED_PATTERNS:
            match = pattern.search(diagnostic.message)
            if match:
                return match.group(1)

        # 2. Extract from range
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
        target_name = cls._extract_name(diagnostic, document)
        if not target_name:
            return None

        diag_line_0 = diagnostic.range.start.line
        diag_line_1 = diag_line_0 + 1
        lines = document.text.splitlines(keepends=True)
        raw_line = lines[diag_line_0] if diag_line_0 < len(lines) else ""

        # Collect defined symbols in the file
        collector = SymbolCollector()
        try:
            tree = ast.parse(document.text)
            collector.visit(tree)
        except Exception:
            # Fallback regex scan for variable assignments and definitions
            for line_idx, line in enumerate(lines):
                for m in re.finditer(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", line):
                    collector._add(m.group(1), line_idx + 1, m.start(1))
                for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=", line):
                    collector._add(m.group(1), line_idx + 1, m.start(1))

        defined_names = set(collector.definitions.keys())

        # Pool of candidate valid names: defined in file + builtins
        candidate_pool = list(defined_names | BUILTIN_NAMES)
        close_matches = difflib.get_close_matches(target_name, candidate_pool, n=3, cutoff=0.6)

        evidence: List[EvidenceItem] = [
            EvidenceItem(
                title=f"Undefined identifier reference '{target_name}'",
                line=diag_line_1,
                column=diagnostic.range.start.character + 1,
                snippet=raw_line.strip(),
                annotation=f"Name '{target_name}' is referenced here but is neither defined in scope nor imported."
            )
        ]

        candidate_fixes: List[CandidateFix] = []

        # Find exact range of the identifier on the line
        target_range = diagnostic.range
        char_start = diagnostic.range.start.character
        char_end = diagnostic.range.end.character
        if char_start == char_end or raw_line[char_start:char_end] != target_name:
            idx = raw_line.find(target_name)
            if idx != -1:
                target_range = Range(
                    start=Position(line=diag_line_0, character=idx),
                    end=Position(line=diag_line_0, character=idx + len(target_name))
                )

        # Case 1: Standard library module missing import
        if target_name in COMMON_STDLIB_MODULES:
            evidence.append(EvidenceItem(
                title=f"Standard library module '{target_name}'",
                line=diag_line_1,
                column=1,
                snippet=f"import {target_name}",
                annotation=f"'{target_name}' is part of Python's standard library but has not been imported."
            ))
            # Insert import at line 0
            import_edit = [
                SourceEdit(
                    range=Range(start=Position(line=0, character=0), end=Position(line=0, character=0)),
                    new_text=f"import {target_name}\n"
                )
            ]
            v_import, p_import = FixVerifier.verify(document.text, import_edit, diagnostic.message)
            candidate_fixes.append(CandidateFix(
                id=f"fix-add-import-{target_name}",
                title=f"Add 'import {target_name}' at top of file",
                description=f"Imports the standard library module '{target_name}'.",
                edits=import_edit,
                verification=v_import,
                diff=FixVerifier.generate_diff(document.text, p_import)
            ))
            explanation_summary = f"Missing import: '{target_name}' is a standard library module."
            explanation_details = (
                f"'{target_name}' is a standard Python library module that must be explicitly imported before use."
            )
            cause_symptom = f"Missing import statement for module '{target_name}'."
            next_steps = f"Add 'import {target_name}' at the top of the file."

        # Case 2: Plausible typo of a defined symbol or builtin
        elif close_matches:
            best_match = close_matches[0]
            if best_match in collector.definitions:
                def_line_1, def_col_0 = collector.definitions[best_match][0]
                def_line_snippet = lines[def_line_1 - 1].strip() if def_line_1 - 1 < len(lines) else ""
                evidence.append(EvidenceItem(
                    title=f"Matching definition of '{best_match}'",
                    line=def_line_1,
                    column=def_col_0 + 1,
                    snippet=def_line_snippet,
                    annotation=f"Defined in this scope at line {def_line_1}."
                ))
            elif best_match in BUILTIN_NAMES:
                evidence.append(EvidenceItem(
                    title=f"Python standard builtin '{best_match}'",
                    line=diag_line_1,
                    column=1,
                    snippet=f"builtins.{best_match}",
                    annotation=f"'{best_match}' is a standard Python built-in function/type."
                ))

            # Candidate fix: replace with best match
            fix_edits = [
                SourceEdit(
                    range=target_range,
                    new_text=best_match
                )
            ]
            verification, p_text = FixVerifier.verify(document.text, fix_edits, diagnostic.message)
            candidate_fixes.append(CandidateFix(
                id=f"fix-replace-typo-{target_name}-with-{best_match}",
                title=f"Change '{target_name}' to '{best_match}'",
                description=f"Replaces likely typographical error '{target_name}' with in-scope name '{best_match}'.",
                edits=fix_edits,
                verification=verification,
                diff=FixVerifier.generate_diff(document.text, p_text)
            ))
            explanation_summary = f"Undefined name: '{target_name}' is not defined in the current scope."
            explanation_details = (
                f"The identifier '{target_name}' referenced at line {diag_line_1} could not be resolved. "
                f"However, the similar name '{close_matches[0]}' is present in scope. "
                f"This suggests a likely typographical error."
            )
            cause_symptom = f"Likely misspelling of '{close_matches[0]}' as '{target_name}'."
            next_steps = f"Replace '{target_name}' with '{close_matches[0]}' or define '{target_name}' before use."
        else:
            explanation_summary = f"Undefined name: '{target_name}' is not defined in the current scope."
            explanation_details = (
                f"The identifier '{target_name}' is referenced at line {diag_line_1} without being defined or imported."
            )
            cause_symptom = f"No symbol named '{target_name}' exists in the current scope."
            next_steps = f"Define '{target_name}' before line {diag_line_1} or verify the spelling."

        explanation = Explanation(
            summary=explanation_summary,
            details=explanation_details,
            cause_vs_symptom=cause_symptom,
            next_steps=next_steps
        )

        return InvestigationResult(
            status="success",
            category="UNDEFINED_NAME",
            diagnostic=diagnostic,
            explanation=explanation,
            evidence=evidence,
            candidate_fixes=candidate_fixes,
            metadata={
                "target_name": target_name,
                "close_matches": close_matches,
                "is_stdlib_module": target_name in COMMON_STDLIB_MODULES
            }
        )
