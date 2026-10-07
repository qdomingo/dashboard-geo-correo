from io import BytesIO
import unittest

import pandas as pd

from geography import DataValidationError, export_csv, export_excel
from responsibles import MASTER_COLUMNS, RESULT_COLUMNS, filter_master, process_responsibles


class ResponsibleTests(unittest.TestCase):
    def setUp(self):
        self.licenses = pd.DataFrame([
            ["x", "Activa", "Business", "2026-01-01", "", "P", "e", "Empresa", "1C", "00123", "Nombre", " ED@MINSAIT.COM "],
            ["x", "Baja", "Enterprise", "2025-01-01", "2026-01-01", "Q", "e", "Empresa", "1C", "00456", "Otro", "otro@indra.es"],
        ], columns=["Columna1", "Estado", "Licencia", "Fecha alta ", "Fecha baja ", "Proyecto", "Elemento", "Empresa", "Cod empresa", "Unnamed: 9", "Nombre completo", "Mail"])
        self.responsible = pd.DataFrame({"CDNEMPRO": ["P"], "CDEMPCSC": ["1C"], "RESPVERTICAL": ["Vertical"], "MAILRESPVERTICAL": ["v@indra.es"], "RESPHORIZONTAL": ["Horizontal"], "MAILRESPHORIZONTAL": ["h@indra.es"]})

    def test_columns_and_left_join_preserve_license_values(self):
        result = process_responsibles(self.licenses, self.responsible)
        self.assertEqual(result.table.columns.tolist(), RESULT_COLUMNS)
        self.assertEqual(len(result.table), 2)
        self.assertEqual(result.table["login"].tolist(), ["ed_indra", "otro_indra"])
        self.assertEqual(result.table["id_empleado"].tolist(), ["00123", "00456"])
        self.assertEqual(result.table["mail"].iloc[0], " ED@MINSAIT.COM ")
        self.assertEqual(result.table["fecha baja"].iloc[1], "2026-01-01")
        self.assertEqual(result.table["Responsable Vertical"].tolist(), ["Vertical", ""])
        self.assertEqual((result.matched, result.unmatched), (1, 1))

    def test_duplicates_do_not_multiply_license_rows(self):
        licenses = pd.concat([self.licenses, self.licenses], ignore_index=True)
        responsible = pd.concat([self.responsible, self.responsible], ignore_index=True)
        self.assertEqual(len(process_responsibles(licenses, responsible).table), 4)

    def test_separate_keys_avoid_concatenation_collisions(self):
        self.licenses.loc[0, ["Proyecto", "Cod empresa"]] = ["A-B", "C"]
        self.responsible.loc[0, ["CDNEMPRO", "CDEMPCSC"]] = ["A", "B-C"]
        self.assertEqual(process_responsibles(self.licenses, self.responsible).matched, 0)

    def test_missing_keys_and_invalid_email_do_not_match(self):
        self.licenses.loc[0, ["Proyecto", "Mail"]] = [None, None]
        self.responsible.loc[0, "CDNEMPRO"] = None
        result = process_responsibles(self.licenses, self.responsible)
        self.assertEqual((result.incomplete_keys, result.invalid_emails, result.matched), (1, 1, 0))
        self.assertEqual(result.table["login"].iloc[0], "")

    def test_conflicting_responsibles_are_blank_and_reported(self):
        different = self.responsible.copy()
        different.loc[0, "RESPVERTICAL"] = "Otro"
        result = process_responsibles(self.licenses, pd.concat([self.responsible, different], ignore_index=True))
        self.assertEqual(result.conflicting_pairs, 1)
        self.assertTrue(result.table.iloc[0, 10:].eq("").all())

    def test_spaces_alias_and_empty_lookup(self):
        self.responsible.rename(columns={"MAILRESPVERTICAL": "milrespvertical"}, inplace=True)
        self.responsible.loc[0, "CDNEMPRO"] = " P "
        self.assertEqual(process_responsibles(self.licenses, self.responsible).matched, 1)
        result = process_responsibles(self.licenses, self.responsible.iloc[:0])
        self.assertEqual(result.unmatched, 2)

    def test_missing_columns_and_empty_licenses_raise(self):
        for licenses in (self.licenses.iloc[:0], self.licenses.iloc[:, :9], self.licenses.drop(columns="Mail")):
            with self.assertRaises(DataValidationError):
                process_responsibles(licenses, self.responsible)

    def test_exports_include_all_columns(self):
        table = process_responsibles(self.licenses, self.responsible).table
        for restored in (pd.read_csv(BytesIO(export_csv(table)), sep=";", dtype=str, keep_default_na=False), pd.read_excel(BytesIO(export_excel(table)), dtype=str, keep_default_na=False)):
            pd.testing.assert_frame_equal(restored, table, check_dtype=False)

    def test_master_removes_canceled_and_preserves_other_rows(self):
        table = pd.concat([process_responsibles(self.licenses, self.responsible).table] * 3, ignore_index=True)
        table["estado de licencia"] = ["Cancelada", " CANCELADA ", "Asignada", "Pendiente", "", None]
        original = table.copy(deep=True)
        master = filter_master(table)
        self.assertEqual(master.columns.tolist(), MASTER_COLUMNS)
        self.assertEqual(len(master), 4)
        self.assertEqual(master["login"].tolist(), table["login"].iloc[2:].tolist())
        self.assertTrue(master["Excluido"].eq(0).all())
        pd.testing.assert_frame_equal(table, original)

    def test_master_marks_repository_only_licenses_as_excluded(self):
        table = pd.concat([process_responsibles(self.licenses, self.responsible).table] * 3, ignore_index=True)
        table["estado de licencia"] = ["Asignada", "Asignada", "Asignada", "Cancelada", "Asignada", "Asignada"]
        table["tipo de licencia"] = ["Github (solo repositorios)", " GITHUB (SOLO REPOSITORIOS) ", "GitHub Copilot", "Github (solo repositorios)", None, ""]
        master = filter_master(table)
        self.assertEqual(master["Excluido"].tolist(), [1, 1, 0, 0, 0])
        self.assertEqual(master.columns.tolist(), MASTER_COLUMNS)
        restored = pd.read_excel(BytesIO(export_excel(master, sheet_name="Maestro")), keep_default_na=False)
        self.assertEqual(restored["Excluido"].tolist(), [1, 1, 0, 0, 0])

    def test_master_all_canceled_keeps_empty_schema(self):
        table = process_responsibles(self.licenses, self.responsible).table
        table["estado de licencia"] = "cancelada"
        master = filter_master(table)
        self.assertTrue(master.empty)
        self.assertEqual(master.columns.tolist(), MASTER_COLUMNS)


if __name__ == "__main__":
    unittest.main()