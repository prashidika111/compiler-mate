import unittest
from compilermate.repair import Repair

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

if __name__ == '__main__':
    unittest.main()
