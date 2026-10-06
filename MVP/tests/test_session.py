import unittest
from compilermate.session import Session

class TestSession(unittest.TestCase):
    def test_state_rebuilt_on_new_compilation(self):
        # First compilation: valid program with x and y
        session = Session(source="int x = 1;\nint y = 2;")
        success = session.compile()
        self.assertTrue(success)
        self.assertEqual(len(session.symbol_table), 2)
        self.assertIsNotNone(session.symbol_table.lookup("x"))
        self.assertIsNotNone(session.symbol_table.lookup("y"))

        # Second compilation: source changed to only define z
        session.source = "int z = 100;"
        success = session.compile()
        self.assertTrue(success)
        self.assertEqual(len(session.symbol_table), 1)
        self.assertIsNone(session.symbol_table.lookup("x"), "Stale symbol x must not persist")
        self.assertIsNone(session.symbol_table.lookup("y"), "Stale symbol y must not persist")
        self.assertIsNotNone(session.symbol_table.lookup("z"))

    def test_state_cleared_on_syntax_error(self):
        # Initial compilation succeeds
        session = Session(source="int x = 1;")
        session.compile()
        self.assertEqual(len(session.symbol_table), 1)

        # Recompile with syntax error
        session.source = "int x = "
        success = session.compile()
        self.assertFalse(success)
        self.assertEqual(len(session.symbol_table), 0, "Symbol table must be empty on failed syntax parse")
        self.assertIsNotNone(session.diagnostic)

    def test_multiline_offset_calculation(self):
        session = Session(source="int x = 1;\nint y = 2;\nint z = 3;")
        # Line 1, Col 1 -> offset 0
        self.assertEqual(session._offset_from_line_col(1, 1), 0)
        # Line 2, Col 1 -> offset len("int x = 1;\n") = 11
        self.assertEqual(session._offset_from_line_col(2, 1), 11)

    def test_apply_repair_invalid_index(self):
        session = Session(source="int x = 10")
        session.compile()
        self.assertFalse(session.apply_repair(-1))
        self.assertFalse(session.apply_repair(99))

    def test_state_cleared_on_lexical_error(self):
        # First compilation succeeds
        session = Session(source="int x = 1;")
        session.compile()
        self.assertEqual(len(session.symbol_table), 1)

        # Second compilation fails at lexical stage
        session.source = "int x @ 1;"
        success = session.compile()
        self.assertFalse(success)
        self.assertIsNotNone(session.diagnostic)
        self.assertEqual(session.diagnostic.phase, "lexical")
        self.assertEqual(len(session.symbol_table), 0)
        self.assertIsNone(session.ast)
        self.assertEqual(len(session.repair_candidates), 0)

    def test_recompilation_after_repair_refreshes_all_state(self):
        session = Session(source="int x = 10")
        session.compile()
        self.assertFalse(session.diagnostic is None)
        self.assertEqual(len(session.repair_candidates), 1)

        # Apply repair
        success = session.apply_repair(0)
        self.assertTrue(success)
        self.assertIsNone(session.diagnostic)
        self.assertEqual(len(session.repair_candidates), 0)
        self.assertIsNotNone(session.ast)
        self.assertEqual(len(session.symbol_table), 1)
        self.assertEqual(session.symbol_table.lookup("x").type, "int")

if __name__ == '__main__':
    unittest.main()
