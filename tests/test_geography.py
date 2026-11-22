from io import BytesIO
import unittest

import pandas as pd
from openpyxl import load_workbook

from geography import DataValidationError, export_csv, export_excel, process_geographies


class GeographyTests(unittest.TestCase):
    def setUp(self):
        self.employees = pd.DataFrame({"LOGIN": ["edomingo_indra", "otro_indra"], "GEOGRAFIA": ["Espa\u00f1a", "Italia"]})

    def test_left_join_deduplicates_users_and_labels_minsait(self):
        licenses = pd.DataFrame({"Mail": ["edomingo@minsait.com", "ausente@indra.es", "edomingo@indra.es"]})
        result = process_geographies(self.employees, licenses)
        self.assertEqual(result.table.columns.tolist(), ["id_empleado", "login", "geograf\u00eda", "Organizaci\u00f3n", "duplicados", "estado de licencia"])
        self.assertEqual(result.table["login"].tolist(), ["edomingo_indra", "ausente_indra"])
        self.assertEqual(result.table["geograf\u00eda"].tolist(), ["Espa\u00f1a", ""])
        self.assertEqual(result.table["Organizaci\u00f3n"].tolist(), ["MINSAIT", "MINSAIT"])
        self.assertEqual(result.table["duplicados"].tolist(), ["", ""])
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
                self.assertEqual(result.table["duplicados"].tolist(), ["duplicado(MINSAIT)" if "Asignada" in states else ""])
                self.assertEqual(result.license_status.str.casefold().tolist(), ["asignada" if "Asignada" in states else "cancelada"])
                self.assertEqual(result.matched, 1)

    def test_case_spaces_and_accented_headers(self):
        employees = pd.DataFrame({" Login ": [" EDOMINGO_INDRA "], "Geograf\u00eda": [" Espa\u00f1a "]})
        result = process_geographies(employees, pd.DataFrame({" MAIL ": [" EDOMINGO@MINSAIT.COM "]}))
        self.assertEqual(result.table.iloc[0].tolist(), ["", "edomingo_indra", "Espa\u00f1a", "MINSAIT", "", ""])

    def test_missing_or_invalid_mail_preserves_blank_rows(self):
        licenses = pd.DataFrame({"Mail": [None, "", "sin-arroba", "@dominio", "a@", "a@@b", "a b@c"]})
        result = process_geographies(self.employees, licenses)
        self.assertEqual(len(result.table), 7)
        self.assertTrue(result.table[["id_empleado", "login", "geograf\u00eda", "duplicados"]].eq("").all().all())
        self.assertEqual(result.invalid_emails, 7)

    def test_duplicate_employees_do_not_multiply_rows(self):
        employees = pd.DataFrame({"login": ["edomingo_indra"] * 3, "geografia": [None, "Espa\u00f1a", "Espa\u00f1a"]})
        result = process_geographies(employees, pd.DataFrame({"mail": ["edomingo@minsait.com"]}))
        self.assertEqual(result.table["geograf\u00eda"].tolist(), ["Espa\u00f1a"])
        self.assertEqual(result.table["duplicados"].tolist(), [""])

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

    def test_induced_join_filters_and_prioritizes_organizations_per_login(self):
        employees = pd.DataFrame({
            "CDEMPLEA": ["01", "02", "03", "03", "04", "05", "06", "06"],
            "LOGIN": ["base_indra", "both_indra", "atm_indra", "atm_indra", "skip_indra", "other_indra", "a_indra", "b_indra"],
            "GEOGRAFIA": ["Spain", "Italy", "", "Portugal", "France", "Brazil", "UK", "UK"],
        })
        licenses = pd.DataFrame({"Mail": ["base@example.com"], "Estado": ["Pendiente"], "id_empleado": ["01"]})
        induced = pd.DataFrame([
            ["01", "Asignada", "ATMPRO", "CAIXABANK"],
            ["02", "Asignada", "ATMPRO", ""],
            ["03", " asignada ", " atmpro ", ""],
            ["03", "Asignada", "ATMPRO", ""],
            ["02", " ASIGNADA ", "OTHER", " caixabank "],
            ["04", "Pendiente", "ATMPRO", "CAIXABANK"],
            ["05", "Asignada", "OTHER", "OTHER"],
            ["06", "Asignada", "ATMPRO", ""],
            ["99", "Asignada", "ATMPRO", ""],
        ], columns=["ID", "Estado", "C\u00f3d. Proyecto", "Cliente"])

        result = process_geographies(employees, licenses, induced)
        self.assertEqual(result.table.values.tolist(), [
            ["01", "base_indra", "Spain", "MINSAIT", "", "Pendiente"],
            ["03", "atm_indra", "Portugal", "ATM", "duplicado(ATM)", "asignada"],
            ["02", "both_indra", "Italy", "CAIXABANK", "duplicado(CAIXABANK-ATM)", "ASIGNADA"],
        ])
        self.assertEqual(result.license_status.tolist(), ["Pendiente", "asignada", "ASIGNADA"])
        self.assertEqual((result.matched, result.unresolved_induced), (3, 2))

    def test_cancelled_minsait_yields_to_induced_only_when_there_is_a_match(self):
        employees = pd.DataFrame({
            "CDEMPLEA": ["01", "02", "03", "04"],
            "LOGIN": ["caixa_indra", "atm_indra", "alone_indra", "active_indra"],
            "GEOGRAFIA": ["Spain"] * 4,
        })
        licenses = pd.DataFrame({
            "Mail": ["caixa@example.com", "atm@example.com", "alone@example.com",
                     "active@example.com", "active@example.com"],
            "Estado": [" CANCELADA ", "Cancelada", "Cancelada", "Cancelada", "Asignada"],
            "id_empleado": ["91", "92", "93", "94", "95"],
        })
        induced = pd.DataFrame([
            ["01", "Asignada", "ATMPRO", ""],
            ["01", "Asignada", "OTHER", "CAIXABANK"],
            ["02", "Asignada", "ATMPRO", ""],
            ["03", "Pendiente", "ATMPRO", ""],
            ["04", "Asignada", "ATMPRO", ""],
        ], columns=["ID", "Estado", "C\u00f3d. Proyecto", "Cliente"])

        result = process_geographies(employees, licenses, induced)
        actual = result.table.set_index("login")
        self.assertTrue(actual.index.is_unique)
        self.assertEqual(actual["duplicados"].to_dict(), {
            "caixa_indra": "duplicado(CAIXABANK-ATM)",
            "atm_indra": "",
            "alone_indra": "",
            "active_indra": "duplicado(MINSAIT-ATM)",
        })
        self.assertEqual(actual[["id_empleado", "Organizaci\u00f3n", "estado de licencia"]].T.to_dict("list"), {
            "caixa_indra": ["01", "CAIXABANK", "Asignada"],
            "atm_indra": ["02", "ATM", "Asignada"],
            "alone_indra": ["93", "MINSAIT", "Cancelada"],
            "active_indra": ["95", "MINSAIT", "Asignada"],
        })

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