from io import BytesIO
import unittest

import pandas as pd
from openpyxl import load_workbook

from geography import DataValidationError, export_csv, export_excel, process_geographies


class GeographyTests(unittest.TestCase):
    def setUp(self):
        self.employees = pd.DataFrame({"LOGIN": ["edomingo_indra", "otro_indra"], "GEOGRAFIA": ["Espa\u00f1a", "Italia"]})

    def test_left_join_deduplicates_users_and_only_three_columns(self):
        licenses = pd.DataFrame({"Mail": ["edomingo@minsait.com", "ausente@indra.es", "edomingo@indra.es"]})
        result = process_geographies(self.employees, licenses)
        self.assertEqual(result.table.columns.tolist(), ["id_empleado", "login", "geograf\u00eda"])
        self.assertEqual(result.table["login"].tolist(), ["edomingo_indra", "ausente_indra"])
        self.assertEqual(result.table["geograf\u00eda"].tolist(), ["Espa\u00f1a", ""])
        self.assertEqual((result.matched, result.unmatched), (1, 1))

    def test_assigned_license_wins_in_both_orders_and_repeated_states(self):
        for states in (["Cancelada", " ASIGNADA ", "Asignada"], ["Asignada", "Cancelada", "Asignada"], ["Cancelada"] * 3):
            with self.subTest(states=states):
                licenses = pd.DataFrame({
                    "Mail": [" EDOMINGO@MINSAIT.COM ", "edomingo@indra.es", "edomingo@minsait.com"],
                    " Estado de licencia ": states,
                }, index=[7, 7, 9])
                result = process_geographies(self.employees, licenses)
                self.assertEqual(result.table["login"].tolist(), ["edomingo_indra"])
                self.assertEqual(result.license_status.str.casefold().tolist(), ["asignada" if "Asignada" in states else "cancelada"])
                self.assertEqual(result.matched, 1)

    def test_case_spaces_and_accented_headers(self):
        employees = pd.DataFrame({" Login ": [" EDOMINGO_INDRA "], "Geograf\u00eda": [" Espa\u00f1a "]})
        result = process_geographies(employees, pd.DataFrame({" MAIL ": [" EDOMINGO@MINSAIT.COM "]}))
        self.assertEqual(result.table.iloc[0].tolist(), ["", "edomingo_indra", "Espa\u00f1a"])

    def test_missing_or_invalid_mail_preserves_blank_rows(self):
        licenses = pd.DataFrame({"Mail": [None, "", "sin-arroba", "@dominio", "a@", "a@@b", "a b@c"]})
        result = process_geographies(self.employees, licenses)
        self.assertEqual(len(result.table), 7)
        self.assertTrue(result.table.eq("").all().all())
        self.assertEqual(result.invalid_emails, 7)

    def test_duplicate_employees_do_not_multiply_rows(self):
        employees = pd.DataFrame({"login": ["edomingo_indra"] * 3, "geografia": [None, "Espa\u00f1a", "Espa\u00f1a"]})
        result = process_geographies(employees, pd.DataFrame({"mail": ["edomingo@minsait.com"]}))
        self.assertEqual(result.table["geograf\u00eda"].tolist(), ["Espa\u00f1a"])

    def test_conflicting_employee_geographies_are_blank_and_reported(self):
        employees = pd.DataFrame({"login": ["edomingo_indra"] * 2, "geografia": ["Italia", "Espa\u00f1a"]})
        result = process_geographies(employees, pd.DataFrame({"mail": ["edomingo@minsait.com"]}))
        self.assertEqual(result.table["geograf\u00eda"].tolist(), [""])
        self.assertEqual(result.conflicting_logins, 1)
        self.assertEqual(result.missing_geography, 0)

    def test_empty_employee_login_never_matches_invalid_mail(self):
        employees = pd.DataFrame({"login": [None, "otro_indra"], "geografia": ["Italia", None]})
        result = process_geographies(employees, pd.DataFrame({"mail": [None, "otro@minsait.com"]}, index=[7, 9]))
        self.assertTrue(result.table["geograf\u00eda"].eq("").all())
        self.assertEqual((result.matched, result.invalid_emails, result.missing_geography), (1, 1, 1))

    def test_missing_and_ambiguous_columns_are_rejected(self):
        for licenses in [pd.DataFrame({"correo": ["a@b"]}), pd.DataFrame([["a@b", "c@d"]], columns=["Mail", " mail "])]:
            with self.assertRaises(DataValidationError):
                process_geographies(self.employees, licenses)

    def test_empty_inputs_are_rejected(self):
        with self.assertRaises(DataValidationError):
            process_geographies(self.employees, pd.DataFrame(columns=["mail"]))

    def test_exports_keep_headers_unicode_and_blanks(self):
        table = process_geographies(self.employees, pd.DataFrame({"mail": ["edomingo@minsait.com", "nadie@indra.es"]})).table
        restored = pd.read_csv(BytesIO(export_csv(table)), sep=";", keep_default_na=False)
        pd.testing.assert_frame_equal(restored, table, check_dtype=False)
        restored_excel = pd.read_excel(BytesIO(export_excel(table)), keep_default_na=False)
        pd.testing.assert_frame_equal(restored_excel, table, check_dtype=False)

    def test_exports_do_not_execute_formulas(self):
        table = pd.DataFrame({"login": ["=unsafe_indra"], "geograf\u00eda": ["=1+1"]})
        self.assertIn("'=1+1", export_csv(table).decode("utf-8-sig"))
        sheet = load_workbook(BytesIO(export_excel(table))).active
        self.assertEqual(sheet["B2"].value, "=1+1")
        self.assertNotEqual(sheet["B2"].data_type, "f")


if __name__ == "__main__":
    unittest.main()