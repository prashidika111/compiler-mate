from typing import Optional
from .ast import ProgramAST, DeclarationAST, AssignmentAST
from .symbol_table import SymbolTable
from .diagnostics import Diagnostic

class SemanticAnalyzer:
    """Performs semantic analysis on the AST.
    Implements exactly four semantic checks:
    1. Redeclaration
    2. Undeclared identifier
    3. Type mismatch in declaration
    4. Type mismatch in assignment

    Stops at the first semantic violation.
    Populates the symbol table on valid declarations.
    """

    def __init__(self, symbol_table: SymbolTable):
        self.symbol_table = symbol_table

    def analyze(self, ast: Optional[ProgramAST]) -> Optional[Diagnostic]:
        if ast is None:
            return None

        for stmt in ast.statements:
            if isinstance(stmt, DeclarationAST):
                diag = self._check_declaration(stmt)
                if diag is not None:
                    return diag
            elif isinstance(stmt, AssignmentAST):
                diag = self._check_assignment(stmt)
                if diag is not None:
                    return diag

        return None

    def _check_declaration(self, stmt: DeclarationAST) -> Optional[Diagnostic]:
        # 1. Redeclaration check
        prev = self.symbol_table.lookup(stmt.name)
        if prev is not None:
            return Diagnostic(
                phase="semantic",
                type="REDECLARATION",
                line=stmt.line,
                column=stmt.column,
                expected="unique identifier",
                actual=f"{stmt.name} already declared as {prev.type} at line {prev.declared_line}",
                message=f"Identifier '{stmt.name}' is already declared",
                symbol=stmt.name
            )

        # 3. Type mismatch in declaration
        if stmt.var_type != stmt.value_type:
            return Diagnostic(
                phase="semantic",
                type="TYPE_MISMATCH_DECL",
                line=stmt.line,
                column=stmt.column,
                expected=stmt.var_type,
                actual=stmt.value_type,
                message=f"Type mismatch in declaration: cannot assign {stmt.value_type} to {stmt.var_type}",
                symbol=stmt.name
            )

        # Successful declaration -> add to symbol table
        self.symbol_table.define(stmt.name, stmt.var_type, stmt.line)
        return None

    def _check_assignment(self, stmt: AssignmentAST) -> Optional[Diagnostic]:
        # 2. Undeclared identifier check for LHS
        target_sym = self.symbol_table.lookup(stmt.name)
        if target_sym is None:
            return Diagnostic(
                phase="semantic",
                type="UNDECLARED_IDENTIFIER",
                line=stmt.line,
                column=stmt.column,
                expected="declared identifier",
                actual=f"'{stmt.name}' is undeclared",
                message=f"Identifier '{stmt.name}' is not declared",
                symbol=stmt.name
            )

        # Evaluate RHS type
        if stmt.is_identifier:
            # Undeclared identifier check for RHS identifier
            rhs_sym = self.symbol_table.lookup(str(stmt.value))
            if rhs_sym is None:
                return Diagnostic(
                    phase="semantic",
                    type="UNDECLARED_IDENTIFIER",
                    line=stmt.rvalue_line,
                    column=stmt.rvalue_column,
                    expected="declared identifier",
                    actual=f"'{stmt.value}' is undeclared",
                    message=f"Identifier '{stmt.value}' is not declared",
                    symbol=str(stmt.value)
                )
            rhs_type = rhs_sym.type
        else:
            rhs_type = stmt.value_type

        # 4. Type mismatch in assignment
        if target_sym.type != rhs_type:
            return Diagnostic(
                phase="semantic",
                type="TYPE_MISMATCH_ASSIGN",
                line=stmt.line,
                column=stmt.column,
                expected=target_sym.type,
                actual=rhs_type,
                message=f"Type mismatch in assignment to '{stmt.name}': expected {target_sym.type}, got {rhs_type}",
                symbol=stmt.name
            )

        return None
