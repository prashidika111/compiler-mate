import sys
from .session import Session

def repl(session: Session):
    """Read‑Eval‑Print Loop for the Review 1 commands.
    The loop runs until the user types "quit" or the compilation succeeds.
    """
    while True:
        try:
            cmd = input('YOU: > ').strip()
        except EOFError:
            break
        if not cmd:
            continue
        lc = cmd.lower()
        if lc == 'quit' or lc == 'exit':
            print('COMPILER: Session terminated.')
            break
        if lc == 'help':
            print('COMPILER: Available commands: explain, suggest fixes, apply 1, help, quit')
            continue
        if lc == 'explain':
            if session.diagnostic:
                d = session.diagnostic
                print(f"COMPILER: {d.message} (expected '{d.expected}', got '{d.actual}') at line {d.line}, column {d.column}.")
            else:
                print('COMPILER: No diagnostic to explain.')
            continue
        if lc == 'suggest fixes' or lc == 'suggest':
            if session.repair_candidates:
                for i, r in enumerate(session.repair_candidates, start=1):
                    print(f"COMPILER: [{i}] {r.description} at line {r.line}, column {r.column}.")
            else:
                print('COMPILER: No suggested fixes.')
            continue
        if lc.startswith('apply'):
            parts = lc.split()
            if len(parts) != 2 or not parts[1].isdigit():
                print('COMPILER: Usage: apply <number>')
                continue
            idx = int(parts[1]) - 1
            success = session.apply_repair(idx)
            if success:
                print('COMPILER: Fix applied. Recompiling...')
                if session.diagnostic is None:
                    print('COMPILER: Compilation successful.')
                    break
                else:
                    print('COMPILER: Compilation still has errors.')
            else:
                print('COMPILER: Invalid repair index.')
            continue
        # optional state command
        if lc == 'state' or lc == 'inspect':
            print('COMPILER: CURRENT COMPILER STATE')
            if session.diagnostic:
                d = session.diagnostic
                print(f'  Phase: {d.phase}\n  Type: {d.type}\n  Line: {d.line}\n  Column: {d.column}\n  Expected: {d.expected}\n  Actual: {d.actual}\n  Message: {d.message}')
            else:
                print('  No diagnostic – compilation succeeded.')
            continue
        print('COMPILER: Unknown command. Type "help" for a list.')
