from .session import Session

def repl(session: Session):
    """Read-Eval-Print Loop for developer-compiler interaction in Phase 2.
    Supports:
    - help
    - explain
    - suggest fixes / suggest
    - apply N
    - show symbols / symbols
    - state / inspect
    - quit / exit
    """
    while True:
        try:
            cmd = input('YOU: > ').strip()
        except EOFError:
            break
        if not cmd:
            continue

        lc = cmd.lower()
        if lc in ('quit', 'exit'):
            print('COMPILER: Session terminated.')
            break

        if lc == 'help':
            print('COMPILER: Available commands: explain, suggest fixes, apply <number>, show symbols, state, help, quit')
            continue

        if lc == 'explain':
            if session.diagnostic:
                d = session.diagnostic
                if d.phase == "semantic":
                    if d.type == "REDECLARATION":
                        print(f"COMPILER: Semantic Error: Identifier '{d.symbol}' is already declared. (expected '{d.expected}', got '{d.actual}') at line {d.line}, column {d.column}.")
                    elif d.type == "UNDECLARED_IDENTIFIER":
                        print(f"COMPILER: Semantic Error: Identifier '{d.symbol}' is not declared. (expected '{d.expected}', got '{d.actual}') at line {d.line}, column {d.column}.")
                    elif d.type == "TYPE_MISMATCH_DECL":
                        print(f"COMPILER: Semantic Error: Type mismatch in declaration of '{d.symbol}'. Cannot assign {d.actual} to {d.expected} at line {d.line}, column {d.column}.")
                    elif d.type == "TYPE_MISMATCH_ASSIGN":
                        print(f"COMPILER: Semantic Error: Type mismatch in assignment to '{d.symbol}'. Expected {d.expected}, got {d.actual} at line {d.line}, column {d.column}.")
                    else:
                        print(f"COMPILER: Semantic Error: {d.message} at line {d.line}, column {d.column}.")
                else:
                    print(f"COMPILER: {d.message} (expected '{d.expected}', got '{d.actual}') at line {d.line}, column {d.column}.")
            else:
                print('COMPILER: No diagnostic to explain.')
            continue

        if lc in ('suggest fixes', 'suggest'):
            if session.repair_candidates:
                for i, r in enumerate(session.repair_candidates, start=1):
                    print(f"COMPILER: [{i}] {r.description} at line {r.line}, column {r.column}.")
            elif session.diagnostic and session.diagnostic.phase == "semantic":
                print('COMPILER: No deterministic repair available for semantic diagnostic.')
            else:
                print('COMPILER: No suggested fixes.')
            continue

        if lc.startswith('apply'):
            parts = lc.split()
            if len(parts) != 2 or not parts[1].isdigit():
                print('COMPILER: Usage: apply <number>')
                continue
            idx = int(parts[1]) - 1
            if idx < 0 or idx >= len(session.repair_candidates):
                print('COMPILER: Invalid repair index.')
                continue
            success = session.apply_repair(idx)
            print('COMPILER: Fix applied. Recompiling...')
            if success:
                print('COMPILER: Compilation successful.')
            else:
                print('COMPILER: Compilation still has errors.')
            continue

        if lc in ('show symbols', 'symbols'):
            symbols = session.symbol_table.all_symbols()
            if symbols:
                print('COMPILER: CURRENT SYMBOL TABLE:')
                print('  NAME       | TYPE  | DECLARED LINE')
                print('  ' + '-' * 35)
                for sym in symbols:
                    print(f'  {sym.name:<10} | {sym.type:<5} | {sym.declared_line}')
            else:
                print('COMPILER: Symbol table is empty.')
            continue

        if lc in ('state', 'inspect'):
            print('COMPILER: CURRENT COMPILER STATE')
            if session.diagnostic:
                d = session.diagnostic
                sym_str = f"\n  Symbol: {d.symbol}" if d.symbol else ""
                print(f'  Phase: {d.phase}\n  Type: {d.type}\n  Line: {d.line}\n  Column: {d.column}\n  Expected: {d.expected}\n  Actual: {d.actual}\n  Message: {d.message}{sym_str}')
            else:
                print('  Status: Compilation succeeded (no diagnostic).')

            symbols = session.symbol_table.all_symbols()
            if symbols:
                print('  Symbol Table:')
                for s in symbols:
                    print(f'    - {s.name}: {s.type} (line {s.declared_line})')
            else:
                print('  Symbol Table: (empty)')
            continue

        print('COMPILER: Unknown command. Type "help" for a list.')
