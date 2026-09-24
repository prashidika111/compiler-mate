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
            self.assertIn("x: int", output)

if __name__ == '__main__':
    unittest.main()
