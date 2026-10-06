import unittest
from unittest.mock import patch
import io
from compilermate.session import Session
from compilermate.interaction import repl

class TestInteraction(unittest.TestCase):
    def test_show_symbols_command(self):
        session = Session(source="int x = 5;\nbool flag = true;")
        session.compile()

        inputs = iter(["show symbols", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("x", output)
            self.assertIn("flag", output)
            self.assertIn("int", output)
            self.assertIn("bool", output)

    def test_explain_command_semantic(self):
        session = Session(source="bool b = 5;")
        session.compile()

        inputs = iter(["explain", "suggest fixes", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("b", output)
            self.assertIn("Type mismatch", output)
            self.assertIn("No deterministic repair available", output)

    def test_apply_command_in_repl(self):
        session = Session(source="int x = 10\nint y = 5;")
        session.compile()

        inputs = iter(["suggest fixes", "apply 1", "show symbols", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("Fix applied. Recompiling...", output)
            self.assertIn("Compilation successful.", output)
            self.assertIn("x", output)
            self.assertIn("y", output)

    def test_state_command(self):
        session = Session(source="int x = 5;")
        session.compile()

        inputs = iter(["state", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("CURRENT COMPILER STATE", output)
            self.assertIn("Status: SUCCESS", output)
            self.assertIn("x: int", output)

    def test_state_command_with_failed_semantic(self):
        session = Session(source="bool b = 5;")
        session.compile()

        inputs = iter(["state", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("CURRENT COMPILER STATE", output)
            self.assertIn("Status: FAILED", output)
            self.assertIn("Pipeline Stage: SEMANTIC", output)
            self.assertIn("Diagnostic Type: TYPE_MISMATCH_DECL", output)
            self.assertIn("Symbol: b", output)

    def test_show_tokens_command(self):
        session = Session(source="int x = 5;")
        session.compile()

        inputs = iter(["show tokens", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("TOKEN STREAM", output)
            self.assertIn("INT", output)
            self.assertIn("IDENTIFIER", output)
            self.assertIn("ASSIGN", output)
            self.assertIn("INT_LITERAL", output)
            self.assertIn("SEMICOLON", output)

    def test_show_tokens_empty(self):
        session = Session(source="")
        # Uncompiled session with empty tokens
        inputs = iter(["show tokens", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("Token stream is empty.", output)

    def test_show_ast_command(self):
        session = Session(source="int x = 5;\nbool flag = true;\nx = 10;")
        session.compile()

        inputs = iter(["show ast", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("ABSTRACT SYNTAX TREE", output)
            self.assertIn("Program", output)
            self.assertIn("Declaration", output)
            self.assertIn("Type: int", output)
            self.assertIn("Name: x", output)
            self.assertIn("Value: 5", output)
            self.assertIn("Type: bool", output)
            self.assertIn("Name: flag", output)
            self.assertIn("Value: true", output)
            self.assertIn("Assignment", output)
            self.assertIn("Target: x", output)
            self.assertIn("Value: 10", output)

    def test_show_ast_when_none(self):
        session = Session(source="int x = ")
        session.compile()

        inputs = iter(["show ast", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("No AST available.", output)

    def test_explain_lexical_error(self):
        session = Session(source="int x @ 5;")
        session.compile()

        inputs = iter(["explain", "suggest fixes", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("Lexical Error", output)
            self.assertIn("Unrecognized character '@'", output)
            self.assertIn("No deterministic repair available for lexical diagnostic.", output)

    def test_explain_syntax_error(self):
        session = Session(source="int x = 10")
        session.compile()

        inputs = iter(["explain", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("Syntax Error", output)
            self.assertIn("Expected ';'", output)

    def test_help_command(self):
        session = Session(source="int x = 1;")
        session.compile()

        inputs = iter(["help", "quit"])
        with patch('builtins.input', lambda _: next(inputs)), patch('sys.stdout', new=io.StringIO()) as fake_out:
            repl(session)
            output = fake_out.getvalue()
            self.assertIn("show tokens", output)
            self.assertIn("show ast", output)
            self.assertIn("show symbols", output)
            self.assertIn("state", output)

if __name__ == '__main__':
    unittest.main()
