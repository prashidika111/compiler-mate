import sys
from typing import Optional
from .session import Session
from .ast import ProgramAST, DeclarationAST, AssignmentAST

def format_ast(ast: Optional[ProgramAST]) -> str:
    """Renders a human-readable tree representation of the ProgramAST."""
    if ast is None:
        return 'COMPILER: No AST available.'
    if not ast.statements:
        return 'COMPILER: ABSTRACT SYNTAX TREE\n\nProgram\n  (empty)'

    # Check if stdout encoding supports box-drawing characters
    use_unicode = True
    try:
        '├──'.encode(sys.stdout.encoding or 'ascii')
    except (UnicodeEncodeError, LookupError, AttributeError):
        use_unicode = False

    t_branch = '├── ' if use_unicode else '+-- '
    l_branch = '└── ' if use_unicode else '\\-- '
    v_bar = '│   ' if use_unicode else '|   '
    sep_bar = '│' if use_unicode else '|'

    lines = ['COMPILER: ABSTRACT SYNTAX TREE', '', 'Program']
    n = len(ast.statements)
    for i, stmt in enumerate(ast.statements):
        is_last_stmt = (i == n - 1)
        branch_stmt = l_branch if is_last_stmt else t_branch
        prefix_child = '    ' if is_last_stmt else v_bar

        if isinstance(stmt, DeclarationAST):
            val_str = str(stmt.value).lower() if isinstance(stmt.value, bool) else str(stmt.value)
            lines.append(f'{branch_stmt}Declaration')
            lines.append(f'{prefix_child}{t_branch}Type: {stmt.var_type}')
            lines.append(f'{prefix_child}{t_branch}Name: {stmt.name}')
            lines.append(f'{prefix_child}{l_branch}Value: {val_str}')
        elif isinstance(stmt, AssignmentAST):
            val_str = str(stmt.value).lower() if isinstance(stmt.value, bool) else str(stmt.value)
            lines.append(f'{branch_stmt}Assignment')
            lines.append(f'{prefix_child}{t_branch}Target: {stmt.name}')
            lines.append(f'{prefix_child}{l_branch}Value: {val_str}')

        if not is_last_stmt:
            lines.append(sep_bar)

    return '\n'.join(lines)

def repl(session: Session):
    """Read-Eval-Print Loop for developer-compiler interaction in CompilerMate.
    Supports:
    - help
    - explain
    - suggest fixes / suggest
    - apply N
    - show symbols / symbols
    - show tokens / tokens
    - show ast / ast
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
            print('COMPILER: Available commands: explain, suggest fixes, apply <number>, show symbols, show tokens, show ast, state, help, quit')
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
                elif d.phase == "lexical":
                    print(f"COMPILER: Lexical Error: {d.message} (expected '{d.expected}', got '{d.actual}') at line {d.line}, column {d.column}.")
                else:
                    print(f"COMPILER: Syntax Error: {d.message} (expected '{d.expected}', got '{d.actual}') at line {d.line}, column {d.column}.")
            else:
                print('COMPILER: No diagnostic to explain.')
            continue

        if lc in ('suggest fixes', 'suggest'):
            if session.repair_candidates:
                for i, r in enumerate(session.repair_candidates, start=1):
                    print(f"COMPILER: [{i}] {r.description} at line {r.line}, column {r.column}.")
            elif session.diagnostic and session.diagnostic.phase == "semantic":
                print('COMPILER: No deterministic repair available for semantic diagnostic.')
            elif session.diagnostic and session.diagnostic.phase == "lexical":
                print('COMPILER: No deterministic repair available for lexical diagnostic.')
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

        if lc in ('show tokens', 'tokens'):
            if session.tokens:
                print('COMPILER: TOKEN STREAM')
                print('  LINE  COLUMN  TYPE          LEXEME')
                print('  ' + '-' * 36)
                for tok in session.tokens:
                    print(f'  {tok.line:<5} {tok.column:<7} {tok.type.name:<13} {tok.lexeme}')
            else:
                print('COMPILER: Token stream is empty.')
            continue

        if lc in ('show ast', 'ast'):
            print(format_ast(session.ast))
            continue

        if lc in ('state', 'inspect'):
            print('COMPILER: CURRENT COMPILER STATE')
            if session.diagnostic:
                d = session.diagnostic
                print('  Status: FAILED')
                print(f'  Pipeline Stage: {d.phase.upper()}')
                print(f'  Diagnostic Type: {d.type}')
                print(f'  Line: {d.line}')
                print(f'  Column: {d.column}')
                if d.symbol:
                    print(f'  Symbol: {d.symbol}')
                print(f'  Expected: {d.expected}')
                print(f'  Actual: {d.actual}')
                print(f'  Message: {d.message}')
            else:
                print('  Status: SUCCESS (no diagnostic)')
                print('  Pipeline Stage: COMPLETE')

            symbols = session.symbol_table.all_symbols()
            if symbols:
                print('  Symbol Table:')
                for s in symbols:
                    print(f'    - {s.name}: {s.type} (line {s.declared_line})')
            else:
                print('  Symbol Table: (empty)')

            if session.repair_candidates:
                print('  Repair Candidates:')
                for i, r in enumerate(session.repair_candidates, start=1):
                    print(f'    [{i}] {r.description} at line {r.line}, column {r.column}')
            else:
                print('  Repair Candidates: None')
            continue

        print('COMPILER: Unknown command. Type "help" for a list.')
