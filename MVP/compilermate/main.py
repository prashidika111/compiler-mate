import sys
from .session import Session
from .interaction import repl

def read_source() -> str:
    """Reads source code from standard input.
    If stdin is a terminal, reads multiline input until an empty line or EOF.
    If stdin is redirected/piped, reads all available content.
    """
    if not sys.stdin.isatty():
        return sys.stdin.read()

    print("Enter source code (end with an empty line or EOF):")
    lines = []
    while True:
        try:
            line = input("SOURCE > " if not lines else "...      > ")
            if not line.strip() and lines:
                break
            lines.append(line)
        except EOFError:
            break
    return "\n".join(lines)

def main():
    header = """==================================================
                   CompilerMate
       Two-Way Developer–Compiler Interaction
=================================================="""
    print(header)
    source = read_source()
    session = Session(source=source)
    success = session.compile()
    if success:
        print('COMPILER: Compilation successful.')
    else:
        d = session.diagnostic
        if d:
            print(f'COMPILER: Error at line {d.line}, column {d.column}: {d.message} (expected "{d.expected}")')

    # Retain active REPL session so user can interact
    repl(session)

if __name__ == '__main__':
    main()
