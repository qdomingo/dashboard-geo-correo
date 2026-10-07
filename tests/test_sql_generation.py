import re
import unittest

import pandas as pd

from geography import DataValidationError
from sql_generation import EMPLOYEES_SQL, generate_responsible_sql


class SQLGenerationTests(unittest.TestCase):
    def test_employee_query_is_static(self):
        self.assertIn("cdalias || '_indra' as login", EMPLOYEES_SQL)
        self.assertEqual(EMPLOYEES_SQL.count("from intdba.empleado int"), 2)
        self.assertIn("\nunion\n", EMPLOYEES_SQL)
        self.assertTrue(EMPLOYEES_SQL.endswith("fesitlab > '01/01/26' and cdalias is not null;"))

    def test_unique_pairs_trimmed_and_missing_rows_omitted(self):
        licenses = pd.DataFrame({" Proyecto ": [" ABAESC ", "ABAESC", "ABAESC", None, "X"], "Cod empresa": ["1C", "1C", "1A", "1C", " "]})
        result = generate_responsible_sql(licenses)
        self.assertEqual((result.unique_pairs, result.blocks, result.omitted_rows), (2, 1, 2))
        self.assertEqual(result.sql.count("'ABAESC-1C'"), 1)
        self.assertIn("'ABAESC-1A'", result.sql)
        self.assertTrue(result.sql.endswith("\n;"))

    def test_oracle_limit_boundaries(self):
        for count in (1, 999, 1000, 1001, 2000, 2001):
            with self.subTest(count=count):
                licenses = pd.DataFrame({"Proyecto": [f"P{index:05}" for index in range(count)], "Cod empresa": ["1C"] * count})
                result = generate_responsible_sql(licenses)
                groups = re.findall(r"dat\.cdnempro \|\| '-' \|\| dat\.cdempcsc in\n\(\n(.*?)\n\)", result.sql, re.S)
                sizes = [len(re.findall(r"'P\d+-1C'", group)) for group in groups]
                self.assertEqual(sum(sizes), count)
                self.assertTrue(all(0 < size <= 1000 for size in sizes))
                self.assertEqual(result.blocks, (count + 999) // 1000)
                self.assertEqual(result.sql.count("\nor "), result.blocks - 1)

    def test_quotes_in_values_are_escaped(self):
        result = generate_responsible_sql(pd.DataFrame({"Proyecto": ["O'NEIL"], "Cod empresa": ["1C"]}))
        self.assertIn("'O''NEIL-1C'", result.sql)

    def test_empty_or_missing_columns_rejected(self):
        for licenses in (pd.DataFrame(columns=["Proyecto", "Cod empresa"]), pd.DataFrame({"Proyecto": [None], "Cod empresa": ["1C"]}), pd.DataFrame({"Proyecto": ["P"]})):
            with self.assertRaises(DataValidationError):
                generate_responsible_sql(licenses)


if __name__ == "__main__":
    unittest.main()