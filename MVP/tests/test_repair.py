import unittest
from compilermate.repair import Repair
from compilermate.session import Session

class TestRepair(unittest.TestCase):
    def test_repair_fields(self):
        r = Repair(
            description="Insert missing semicolon",
            operation="INSERT",
            text=";",
            line=1,
            column=11,
        )
        self.assertEqual(r.description, "Insert missing semicolon")
        self.assertEqual(r.operation, "INSERT")
        self.assertEqual(r.text, ";")
        self.assertEqual(r.line, 1)
        self.assertEqual(r.column, 11)

    def test_no_repair_for_semantic_error(self):
        source = "bool b = 5;"
        session = Session(source=source)
        success = session.compile()
        self.assertFalse(success)
        self.assertIsNotNone(session.diagnostic)
        self.assertEqual(session.diagnostic.phase, "semantic")
        # Semantic error should have 0 repair candidates
        self.assertEqual(len(session.repair_candidates), 0)

if __name__ == '__main__':
    unittest.main()
