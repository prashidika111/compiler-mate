import sys
from .session import Session
from .interaction import repl

def main():
    header = """==================================================
                 CompilerMate
       Two-Way Developer–Compiler Interaction
=================================================="""
    print(header)
    # Prompt for source code (single line for Review 1)
    source = input('SOURCE > ')
    session = Session(source=source)
    success = session.compile()
    if success:
        print('COMPILER: Compilation successful.')
        return
    # Show first error automatically
    d = session.diagnostic
    print(f'COMPILER: Error at line {d.line}, column {d.column}: expected "{d.expected}"')
    # Enter REPL for interaction
    repl(session)

if __name__ == '__main__':
    main()
