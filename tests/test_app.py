from pathlib import Path
from io import BytesIO
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from geography import export_csv, export_excel
from sql_generation import EMPLOYEES_SQL, generate_responsible_sql
from responsibles import RESULT_COLUMNS, filter_master, process_responsibles
import pandas as pd
from email_check import check_emails


ROOT = Path(__file__).resolve().parents[1]


class GeographyDisplayTests(unittest.TestCase):
    def test_status_is_display_only_and_assigned_users_are_deduplicated(self):
        with TemporaryDirectory() as folder:
            input_folder = Path(folder)
            pd.DataFrame({"LOGIN": ["usuario_indra"], "GEOGRAFIA": ["Italia"]}).to_excel(input_folder / "Empleados.xlsx", index=False)
            pd.DataFrame({"Mail": ["usuario@example.com", "usuario@example.com", "otro@example.com"], "Estado": ["Cancelada", "Asignada", "Pendiente"]}).to_excel(input_folder / "Licencias.xlsx", index=False)
            source = (ROOT / "app.py").read_text(encoding="utf-8").replace(
                'INPUT_FOLDER = ROOT / "Archivos_Entrada"', f"INPUT_FOLDER = Path({folder!r})"
            )
            with patch("geography.export_excel", wraps=export_excel) as excel_export, patch("geography.export_csv", wraps=export_csv) as csv_export:
                app = AppTest.from_string(source, default_timeout=30).run()
                app.button(key="process_geographies").click().run()
                self.assertEqual(len(app.exception), 0)
                view = app.dataframe[0].value
                self.assertEqual(view.columns.tolist(), ["login", "geograf\u00eda", "estado de licencia"])
                self.assertEqual(view["estado de licencia"].tolist(), ["Asignada", "Pendiente"])
                self.assertEqual(view["login"].tolist(), ["usuario_indra", "otro_indra"])
                excel_table = excel_export.call_args.args[0]
                csv_table = csv_export.call_args.args[0]
                for restored in (pd.read_excel(BytesIO(export_excel(excel_table))), pd.read_csv(BytesIO(export_csv(csv_table)), sep=";")):
                    self.assertEqual(restored.columns.tolist(), ["login", "geograf\u00eda"])
                    self.assertEqual(restored["login"].tolist(), ["usuario_indra", "otro_indra"])
                app.text_input(key="search").set_value("usuario").run()
                self.assertEqual(app.dataframe[0].value["estado de licencia"].tolist(), ["Asignada"])


class MasterDisplayTests(unittest.TestCase):
    def test_master_shows_repeated_users_but_exports_only_requested_columns(self):
        with TemporaryDirectory() as folder:
            input_folder = Path(folder)
            licenses = pd.DataFrame([
                ["x", "Asignada", "GitHub Copilot", "2026-01-01", "", "P", "e", "Empresa", "1C", "001", "Usuario", "usuario@example.com"],
                ["x", "Asignada", "Github (solo repositorios)", "2026-01-01", "", "P", "e", "Empresa", "1C", "001", "Usuario", "usuario@example.com"],
                ["x", "Asignada", "GitHub Copilot", "2026-01-01", "", "P", "e", "Empresa", "1C", "002", "Otro", "otro@example.com"],
            ], columns=["Columna1", "Estado", "Licencia", "Fecha alta", "Fecha baja", "Proyecto", "Elemento", "Empresa", "Cod empresa", "ID", "Nombre completo", "Mail"])
            licenses.to_excel(input_folder / "Licencias.xlsx", index=False)
            pd.DataFrame({"CDNEMPRO": ["P"], "CDEMPCSC": ["1C"], "RESPVERTICAL": ["Vertical"], "MAILRESPVERTICAL": ["v@example.com"], "RESPHORIZONTAL": ["Horizontal"], "MAILRESPHORIZONTAL": ["h@example.com"]}).to_excel(input_folder / "Responsables.xlsx", index=False)
            source = (ROOT / "app.py").read_text(encoding="utf-8").replace(
                'INPUT_FOLDER = ROOT / "Archivos_Entrada"', f"INPUT_FOLDER = Path({folder!r})"
            )
            with patch("geography.export_excel", wraps=export_excel) as excel_export:
                app = AppTest.from_string(source, default_timeout=30).run()
                app.button(key="process_responsibles").click().run()
                app.button(key="filter_master").click().run()
                self.assertEqual(len(app.exception), 0)
                master = app.dataframe[2].value
                self.assertEqual(master["Repetidos"].tolist(), [1, 1, 0])
                self.assertIn("id_empleado", master.columns)
                self.assertIn("tipo de licencia", master.columns)
                exported = excel_export.call_args.args[0]
                restored = pd.read_excel(BytesIO(export_excel(exported, sheet_name="Maestro")), keep_default_na=False)
                self.assertEqual(restored.columns.tolist(), ["login", "proyecto", "mail", "Mail Responsable Vertical", "Mail Responsable Horizontal", "Excluido"])
                self.assertEqual(restored["login"].tolist(), master["login"].tolist())
                self.assertEqual(restored["Excluido"].tolist(), [0, 1, 0])


@unittest.skipUnless((ROOT / "Archivos_Entrada" / "Empleados.xlsx").exists() and (ROOT / "Archivos_Entrada" / "Licencias.xlsx").exists(), "Requiere Excel locales")
class AppTests(unittest.TestCase):
    def test_process_filter_and_invalidate_with_real_files(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.title[0].value, "Extracci\u00f3n Geograf\u00edas y Correos")
        self.assertFalse(app.button(key="process_geographies").disabled)
        app.button(key="process_geographies").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0, [error.value for error in app.error])
        result = app.session_state["geography_result"]
        self.assertFalse(result.table.loc[result.table["login"].ne(""), "login"].duplicated().any())
        self.assertGreater(len(result.table), 0)
        self.assertEqual(result.table.columns.tolist(), ["login", "geograf\u00eda"])
        geography_view = app.dataframe[0].value
        self.assertEqual(geography_view.columns.tolist(), ["login", "geograf\u00eda", "estado de licencia"])
        licenses_source = pd.read_excel(ROOT / "Archivos_Entrada" / "Licencias.xlsx", sheet_name="O-Licencias", dtype=str, keep_default_na=False)
        source_logins = licenses_source["Mail"].str.strip().str.casefold().str.split("@", n=1).str[0] + "_indra"
        assigned_logins = source_logins.loc[licenses_source["Estado"].str.strip().str.casefold().eq("asignada")]
        assigned_view = geography_view.loc[geography_view["login"].isin(assigned_logins), "estado de licencia"]
        self.assertTrue(assigned_view.str.casefold().eq("asignada").all())
        print(f"Datos reales: {len(result.table)} filas, {result.matched} coincidencias, {result.unmatched} no encontrados, {result.invalid_emails} mails invalidos, {result.missing_geography} empleados sin geografia")
        app.text_input(key="search").set_value("___usuario_inexistente___").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.dataframe[0].value), 0)
        app.button(key="generate_employee_sql").click().run()
        self.assertEqual(app.text_area(key="sql_text").value, EMPLOYEES_SQL)
        app.button(key="generate_responsible_sql").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0, [error.value for error in app.error])
        licenses = pd.read_excel(ROOT / "Archivos_Entrada" / "Licencias.xlsx", sheet_name="O-Licencias", dtype=str, keep_default_na=False)
        expected = generate_responsible_sql(licenses)
        self.assertEqual(app.text_area(key="sql_text").value, expected.sql)
        print(f"SQL Responsables real: {expected.unique_pairs} parejas, {expected.blocks} bloques, {expected.omitted_rows} filas omitidas")
        if (ROOT / "Archivos_Entrada" / "Responsables.xlsx").exists():
            app.button(key="process_responsibles").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 0, [error.value for error in app.error])
            responsible = pd.read_excel(ROOT / "Archivos_Entrada" / "Responsables.xlsx", dtype=str, keep_default_na=False)
            expected_responsibles = process_responsibles(licenses, responsible)
            actual_responsibles = app.session_state["responsible_result"]
            pd.testing.assert_frame_equal(actual_responsibles.table, expected_responsibles.table)
            self.assertEqual(actual_responsibles.table.columns.tolist(), RESULT_COLUMNS)
            self.assertEqual(len(actual_responsibles.table), len(licenses))
            print(f"Responsables real: {len(actual_responsibles.table)} filas, {actual_responsibles.matched} coincidencias, {actual_responsibles.unmatched} no encontrados, {actual_responsibles.incomplete_keys} claves incompletas, {actual_responsibles.conflicting_pairs} parejas contradictorias")
            app.text_input(key="responsible_search").set_value("___usuario_inexistente___").run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.dataframe[1].value), 0)
            app.button(key="filter_master").click().run()
            self.assertEqual(len(app.exception), 0)
            master = app.session_state["master_table"]
            pd.testing.assert_frame_equal(master, filter_master(actual_responsibles.table))
            self.assertEqual(len(app.dataframe[2].value), len(master))
            print(f"Maestro real: {len(master)} filas, {int(master['Excluido'].sum())} excluidas, {len(actual_responsibles.table) - len(master)} canceladas retiradas")
            csv_paths = sorted((ROOT / "Archivos_Entrada").glob("*.csv"))
            if csv_paths:
                app.button(key="check_emails").click().run()
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(len(app.error), 0, [error.value for error in app.error])
                checked = app.session_state["email_result"]
                activity = pd.read_csv(csv_paths[0], dtype=str, keep_default_na=False)
                expected_emails = check_emails(licenses, activity, checked.evaluation_date)
                pd.testing.assert_frame_equal(checked.table, expected_emails.table)
                self.assertEqual(len(checked.table), len(activity))
                print(f"Correos real: {len(checked.table)} usuarios, {int(checked.table['env\u00edo'].eq('SI').sum())} SI, {checked.duplicate_assigned} usuarios con asignadas duplicadas")
                print(checked.table["motivo"].value_counts().to_dict())
                app.toggle(key="email_only_send").set_value(True).run()
                self.assertEqual(len(app.exception), 0)
                self.assertTrue(app.dataframe[3].value["env\u00edo"].eq("SI").all())
        app.toggle(key="use_local_files").set_value(False).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.button(key="process_geographies").disabled)
        self.assertNotIn("geography_result", app.session_state)
        self.assertNotIn("responsible_result", app.session_state)
        self.assertNotIn("master_table", app.session_state)
        self.assertNotIn("email_result", app.session_state)
        self.assertTrue(app.button(key="process_responsibles").disabled)
        self.assertEqual(app.text_area(key="sql_text").value, "")
        self.assertTrue(app.button(key="generate_responsible_sql").disabled)
        self.assertFalse(app.button(key="generate_employee_sql").disabled)
        app.button(key="generate_employee_sql").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.text_area(key="sql_text").value, EMPLOYEES_SQL)


if __name__ == "__main__":
    unittest.main()