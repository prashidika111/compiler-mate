from dataclasses import dataclass
from typing import Dict, Optional, List

@dataclass
class Symbol:
    name: str
    type: str          # "int" or "bool"
    declared_line: int

class SymbolTable:
    """Single global symbol table for Phase 2.
    Stores name, type, and declared_line for declared variables.
    Rebuilt on every compilation.
    """
    def __init__(self):
        self._symbols: Dict[str, Symbol] = {}

    def define(self, name: str, type_: str, declared_line: int) -> None:
        self._symbols[name] = Symbol(name=name, type=type_, declared_line=declared_line)

    def lookup(self, name: str) -> Optional[Symbol]:
        return self._symbols.get(name)

    def all_symbols(self) -> List[Symbol]:
        return list(self._symbols.values())

    def clear(self) -> None:
        self._symbols.clear()

    def __contains__(self, name: str) -> bool:
        return name in self._symbols

    def __len__(self) -> int:
        return len(self._symbols)
