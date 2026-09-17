from dataclasses import dataclass, field
from typing import Optional, List
from .lexer import Lexer
from .parser import Parser
from .diagnostics import Diagnostic
from .repair import Repair
@dataclass
class Session:
    """Keeps the compiler state across the interaction.
    Holds the source code, lexer tokens, any diagnostic, the AST (if parsing succeeds),
    and a list of repair candidates derived from the diagnostic.
    """
    source: str = ""
    tokens: List = field(default_factory=list)
    diagnostic: Optional[Diagnostic] = None
    ast: Optional[object] = None
    repair_candidates: List[Repair] = field(default_factory=list)
    def compile(self) -> bool:
        """Run the lexer and parser on the current ``source``.
        Returns ``True`` when compilation succeeds (no diagnostic).
        Populates ``tokens``, ``ast`` and ``diagnostic`` and generates repair candidates
        for the specific MISSING_TOKEN case.
        """
        lexer = Lexer(self.source)
        self.tokens = lexer.lex()
        parser = Parser(self.tokens)
        self.ast = parser.parse()
        self.diagnostic = parser.diagnostic
        # Reset repair list each compile
        self.repair_candidates.clear()
        if self.diagnostic:
            if (
                self.diagnostic.type == "MISSING_TOKEN"
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
        return self.diagnostic is None
    def _offset_from_line_col(self, line: int, column: int) -> int:
        """Convert a (line, column) pair to a zero‑based string offset.
        The MVP only supports a single‑line source; any line > 1 is treated as the end.
        """
        if line != 1:
            return len(self.source)
        # column is 1‑based; clamp to source length
        offset = column - 1
        return min(offset, len(self.source))
    def apply_repair(self, index: int) -> bool:
        """Apply the repair at ``index`` (0‑based) to the current source.
        Uses the helper to compute the insertion point, updates ``source`` and
        re‑runs ``compile``. Returns ``True`` if recompilation succeeds.
        """
        if index < 0 or index >= len(self.repair_candidates):
            return False
        repair = self.repair_candidates[index]
        offset = self._offset_from_line_col(repair.line, repair.column)
        self.source = self.source[:offset] + repair.text + self.source[offset:]
        return self.compile()
