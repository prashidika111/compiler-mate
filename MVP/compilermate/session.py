from dataclasses import dataclass, field
from typing import Optional, List
from .lexer import Lexer
from .parser import Parser
from .ast import ProgramAST
from .symbol_table import SymbolTable
from .semantic import SemanticAnalyzer
from .diagnostics import Diagnostic
from .repair import Repair

@dataclass
class Session:
    """Keeps the compiler state across the interaction.
    Holds the source code, lexer tokens, AST, symbol table, any diagnostic,
    and a list of repair candidates.
    The entire compiler state is rebuilt on every compilation.
    """
    source: str = ""
    tokens: List = field(default_factory=list)
    ast: Optional[ProgramAST] = None
    symbol_table: SymbolTable = field(default_factory=SymbolTable)
    diagnostic: Optional[Diagnostic] = None
    repair_candidates: List[Repair] = field(default_factory=list)

    def compile(self) -> bool:
        """Runs the compiler pipeline:
        1. Lexer -> tokens
        2. Parser -> AST + syntax diagnostic
        3. Semantic Analyzer -> semantic diagnostic + symbol table population
        Returns True when compilation succeeds without errors.
        """
        # Reset state cleanly on every compilation
        self.tokens.clear()
        self.ast = None
        self.symbol_table.clear()
        self.diagnostic = None
        self.repair_candidates.clear()

        # Step 1: Lexical analysis
        lexer = Lexer(self.source)
        self.tokens = lexer.lex()
        if lexer.diagnostic is not None:
            self.diagnostic = lexer.diagnostic
            return False

        # Step 2: Parsing
        parser = Parser(self.tokens)
        self.ast = parser.parse()
        self.diagnostic = parser.diagnostic

        # Step 3: Syntax repair candidates (only for deterministic syntax errors)
        if self.diagnostic is not None:
            if (
                self.diagnostic.phase == "syntax"
                and self.diagnostic.type == "MISSING_TOKEN"
                and self.diagnostic.expected == ";"
            ):
                repair = Repair(
                    description="Insert missing semicolon",
                    operation="INSERT",
                    text=";",
                    line=self.diagnostic.line,
                    column=self.diagnostic.column,
                )
                self.repair_candidates.append(repair)
            return False

        # Step 4: Semantic analysis
        analyzer = SemanticAnalyzer(self.symbol_table)
        self.diagnostic = analyzer.analyze(self.ast)

        # Semantic diagnostics never receive automated repairs
        return self.diagnostic is None

    def _offset_from_line_col(self, line: int, column: int) -> int:
        """Convert a (line, column) 1-based pair to a 0-based character offset
        in the multiline source string.
        """
        lines = self.source.splitlines(keepends=True)
        if line < 1:
            return 0
        if line > len(lines):
            return len(self.source)

        # Calculate offset up to the target line
        offset = sum(len(lines[i]) for i in range(line - 1))

        # Add column offset within target line
        current_line_text = lines[line - 1]
        col_offset = min(max(0, column - 1), len(current_line_text))
        return offset + col_offset

    def apply_repair(self, index: int) -> bool:
        """Apply the repair candidate at index (0-based) to the current source,
        modifying the source and genuinely recompiling the entire pipeline.
        Returns True if recompilation succeeds.
        """
        if index < 0 or index >= len(self.repair_candidates):
            return False

        repair = self.repair_candidates[index]
        offset = self._offset_from_line_col(repair.line, repair.column)
        self.source = self.source[:offset] + repair.text + self.source[offset:]
        return self.compile()
