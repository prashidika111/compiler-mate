import unittest
from compilermate.session import Session
from compilermate.ast import ProgramAST, DeclarationAST

class TestMVPIntegration(unittest.TestCase):
    def test_full_flow_missing_semicolon(self):
        # Step 1: initial source without semicolon
        src = "int x = 10"
        session = Session(source=src)
        # First compilation should fail
        first_success = session.compile()
        self.assertFalse(first_success, "First compilation should fail due to missing semicolon")
        # Diagnostic should be retained and have correct fields
        diag = session.diagnostic
        self.assertIsNotNone(diag)
        self.assertEqual(diag.phase, "syntax")
        self.assertEqual(diag.type, "MISSING_TOKEN")
        self.assertEqual(diag.expected, ";")
        self.assertEqual(diag.actual, "EOF")
        self.assertEqual(diag.line, 1)
        self.assertEqual(diag.column, 11)
        # Repair candidate should be generated
        self.assertEqual(len(session.repair_candidates), 1)
        repair = session.repair_candidates[0]
        self.assertEqual(repair.text, ";")
        self.assertEqual(repair.line, 1)
        self.assertEqual(repair.column, 11)
        # Apply the repair (index 0)
        applied = session.apply_repair(0)
        self.assertTrue(applied, "Repair application should succeed and recompile")
        # After applying, source should be corrected
        self.assertEqual(session.source, "int x = 10;")
        # Second compilation should succeed
        self.assertTrue(session.diagnostic is None, "No diagnostic after successful recompilation")
        self.assertIsNotNone(session.ast)
        # Verify AST values
        self.assertIsInstance(session.ast, ProgramAST)
        self.assertEqual(len(session.ast.statements), 1)
        decl = session.ast.statements[0]
        self.assertIsInstance(decl, DeclarationAST)
        self.assertEqual(decl.var_type, "int")
        self.assertEqual(decl.name, "x")
        self.assertEqual(decl.value, 10)
        # Symbol table populated
        self.assertEqual(len(session.symbol_table), 1)
        self.assertEqual(session.symbol_table.lookup("x").type, "int")

if __name__ == '__main__':
    unittest.main()
