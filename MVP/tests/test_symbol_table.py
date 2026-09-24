import unittest
from compilermate.symbol_table import SymbolTable, Symbol

class TestSymbolTable(unittest.TestCase):
    def test_define_and_lookup(self):
        st = SymbolTable()
        st.define("x", "int", 1)
        sym = st.lookup("x")
        self.assertIsNotNone(sym)
        self.assertEqual(sym.name, "x")
        self.assertEqual(sym.type, "int")
        self.assertEqual(sym.declared_line, 1)

    def test_lookup_nonexistent(self):
        st = SymbolTable()
        self.assertIsNone(st.lookup("y"))

    def test_all_symbols_and_clear(self):
        st = SymbolTable()
        st.define("x", "int", 1)
        st.define("flag", "bool", 2)
        symbols = st.all_symbols()
        self.assertEqual(len(symbols), 2)
        names = [s.name for s in symbols]
        self.assertIn("x", names)
        self.assertIn("flag", names)

        st.clear()
        self.assertEqual(len(st.all_symbols()), 0)
        self.assertIsNone(st.lookup("x"))

if __name__ == '__main__':
    unittest.main()
