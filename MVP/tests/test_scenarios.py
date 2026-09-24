import unittest
from compilermate.session import Session
from compilermate.ast import ProgramAST, DeclarationAST, AssignmentAST

class TestScenarios(unittest.TestCase):
    def test_scenario_1_valid_program(self):
        """SCENARIO 1 — VALID PROGRAM
        Source:
        int x = 5;
        bool flag = true;
        x = 10;
        Expected:
        - compilation succeeds
        - symbol table contains x and flag
        - show symbols works after successful compilation
        """
        source = "int x = 5;\nbool flag = true;\nx = 10;"
        session = Session(source=source)
        success = session.compile()

        self.assertTrue(success)
        self.assertIsNone(session.diagnostic)
        self.assertEqual(len(session.symbol_table), 2)

        sym_x = session.symbol_table.lookup("x")
        self.assertIsNotNone(sym_x)
        self.assertEqual(sym_x.type, "int")
        self.assertEqual(sym_x.declared_line, 1)

        sym_flag = session.symbol_table.lookup("flag")
        self.assertIsNotNone(sym_flag)
        self.assertEqual(sym_flag.type, "bool")
        self.assertEqual(sym_flag.declared_line, 2)

    def test_scenario_2_type_mismatch(self):
        """SCENARIO 2 — TYPE MISMATCH
        Source:
        bool b = 5;
        Expected:
        - semantic diagnostic
        - type mismatch declaration
        - explain works (proper fields)
        - suggest fixes indicates no deterministic repair
        - state exposes semantic diagnostic/state
        """
        source = "bool b = 5;"
        session = Session(source=source)
        success = session.compile()

        self.assertFalse(success)
        self.assertIsNotNone(session.diagnostic)
        self.assertEqual(session.diagnostic.phase, "semantic")
        self.assertEqual(session.diagnostic.type, "TYPE_MISMATCH_DECL")
        self.assertEqual(session.diagnostic.symbol, "b")
        self.assertEqual(session.diagnostic.expected, "bool")
        self.assertEqual(session.diagnostic.actual, "int")
        # No repairs for semantic errors
        self.assertEqual(len(session.repair_candidates), 0)

    def test_scenario_3_undeclared_identifier(self):
        """SCENARIO 3 — UNDECLARED IDENTIFIER
        Source:
        y = 1;
        Expected:
        - semantic diagnostic
        - symbol = y
        - explain works
        - no deterministic semantic repair
        """
        source = "y = 1;"
        session = Session(source=source)
        success = session.compile()

        self.assertFalse(success)
        self.assertIsNotNone(session.diagnostic)
        self.assertEqual(session.diagnostic.phase, "semantic")
        self.assertEqual(session.diagnostic.type, "UNDECLARED_IDENTIFIER")
        self.assertEqual(session.diagnostic.symbol, "y")
        self.assertEqual(len(session.repair_candidates), 0)

    def test_scenario_4_redeclaration(self):
        """SCENARIO 4 — REDECLARATION
        Source:
        int x = 1;
        int x = 2;
        Expected:
        - redeclaration diagnostic
        - symbol = x
        - diagnostic identifies previous declaration appropriately
        """
        source = "int x = 1;\nint x = 2;"
        session = Session(source=source)
        success = session.compile()

        self.assertFalse(success)
        self.assertIsNotNone(session.diagnostic)
        self.assertEqual(session.diagnostic.phase, "semantic")
        self.assertEqual(session.diagnostic.type, "REDECLARATION")
        self.assertEqual(session.diagnostic.symbol, "x")
        self.assertEqual(session.diagnostic.expected, "unique identifier")
        self.assertEqual(session.diagnostic.actual, "x already declared as int at line 1")

    def test_scenario_5_syntax_repair_and_real_recompilation(self):
        """SCENARIO 5 — SYNTAX REPAIR + REAL RECOMPILATION
        Source:
        int x = 10
        int y = 5;
        Expected:
        - syntax diagnostic for missing semicolon
        - suggest fixes offers deterministic repair
        - apply 1 modifies actual source
        - compiler genuinely recompiles
        - resulting source succeeds
        - symbol table contains x and y
        - show symbols works
        """
        source = "int x = 10\nint y = 5;"
        session = Session(source=source)
        success = session.compile()

        self.assertFalse(success)
        self.assertIsNotNone(session.diagnostic)
        self.assertEqual(session.diagnostic.phase, "syntax")
        self.assertEqual(session.diagnostic.type, "MISSING_TOKEN")
        self.assertEqual(session.diagnostic.expected, ";")

        # Repair candidate available
        self.assertEqual(len(session.repair_candidates), 1)
        repair = session.repair_candidates[0]
        self.assertEqual(repair.text, ";")

        # Apply repair 0
        applied = session.apply_repair(0)
        self.assertTrue(applied)
        self.assertIsNone(session.diagnostic)
        self.assertIn(";", session.source)

        # Symbol table populated with both x and y
        self.assertEqual(len(session.symbol_table), 2)
        sym_x = session.symbol_table.lookup("x")
        self.assertIsNotNone(sym_x)
        self.assertEqual(sym_x.type, "int")

        sym_y = session.symbol_table.lookup("y")
        self.assertIsNotNone(sym_y)
        self.assertEqual(sym_y.type, "int")

if __name__ == '__main__':
    unittest.main()
