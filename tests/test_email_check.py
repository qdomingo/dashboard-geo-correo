import unittest

import pandas as pd

from email_check import EMAIL_COLUMNS, check_emails
from geography import DataValidationError


class EmailCheckTests(unittest.TestCase):
    def evaluate(self, last_activity="2026-09-23T18:00:00Z", high_date="2026-09-23", state="Asignada", kind="Copilot"):
        licenses = pd.DataFrame({"Mail": [" User@minsait.com "], "Estado": [state], "Licencia": [kind], "Fecha alta ": [high_date]})
        activity = pd.DataFrame({"Login": [" USER_INDRA "], "Last Activity At": [last_activity]})
        return check_emails(licenses, activity, today="2026-10-07")

    def test_activity_boundary_and_future(self):
        for date, expected in [("2026-09-23T23:59:00Z", "SI"), ("2026-09-24T00:00:00Z", "NO"), ("2026-10-08T00:00:00Z", "NO")]:
            result = self.evaluate(last_activity=date)
            self.assertEqual(result.table["env\u00edo"].iloc[0], expected)
        self.assertEqual(self.evaluate().table["motivo"].iloc[0], "Sin actividad m\u00e1s de 14 d\u00edas")

    def test_never_used_uses_signup_not_authentication(self):
        for missing in ("None", "none", "", None):
            self.assertEqual(self.evaluate(last_activity=missing, high_date="23/09/2026").table["env\u00edo"].iloc[0], "SI")
            self.assertEqual(self.evaluate(last_activity=missing, high_date="24/09/2026").table["env\u00edo"].iloc[0], "NO")
        self.assertEqual(self.evaluate(last_activity="None").table["motivo"].iloc[0], "A\u00fan no usado")

    def test_repository_only_never_sends(self):
        row = self.evaluate(kind=" GITHUB (SOLO REPOSITORIOS) ").table.iloc[0]
        self.assertEqual((row["env\u00edo"], row["motivo"]), ("NO", "S\u00f3lo Repositorios"))

    def test_canceled_only_is_unmatched_and_other_states_do_not_send(self):
        row = self.evaluate(state=" CANCELADA ").table.iloc[0]
        self.assertEqual((row["mail"], row["env\u00edo"], row["motivo"]), ("", "NO", "Sin coincidencia en licencias"))
        self.assertEqual(self.evaluate(state="Pendiente").table["env\u00edo"].iloc[0], "NO")

    def test_duplicate_assigned_flagged_without_multiplying_csv(self):
        licenses = pd.DataFrame({"mail": ["u@a", "u@a", "u@a", "v@a", "v@a"], "estado": ["Asignada", "Asignada", "Cancelada", "Cancelada", "Asignada"], "licencia": ["Copilot"] * 5, "fecha alta": ["2026-01-01"] * 5})
        activity = pd.DataFrame({"Login": ["u_indra", "v_indra", "missing_indra", "v_indra"], "Last Activity At": ["None"] * 4})
        result = check_emails(licenses, activity, "2026-10-07")
        self.assertEqual(result.table.columns.tolist(), EMAIL_COLUMNS)
        self.assertEqual(len(result.table), 4)
        self.assertEqual(result.duplicate_assigned, 1)
        self.assertEqual(result.table["env\u00edo"].tolist(), ["NO", "SI", "NO", "SI"])
        self.assertEqual(result.table["motivo"].iloc[0], "M\u00e1s de una licencia asignada")

    def test_invalid_dates_do_not_trigger_email(self):
        for arguments in ({"last_activity": "invalid"}, {"last_activity": "None", "high_date": ""}):
            result = self.evaluate(**arguments)
            self.assertEqual(result.table["env\u00edo"].iloc[0], "NO")
            self.assertIn("no valida", result.table["motivo"].iloc[0])

    def test_empty_licenses_keep_all_csv_users(self):
        activity = pd.DataFrame({"Login": ["a_indra"], "Last Activity At": ["None"]})
        result = check_emails(pd.DataFrame(columns=["mail", "estado", "licencia", "fecha alta"]), activity, "2026-10-07")
        self.assertEqual(result.table["motivo"].tolist(), ["Sin coincidencia en licencias"])

    def test_required_columns_and_empty_csv(self):
        with self.assertRaises(DataValidationError):
            check_emails(pd.DataFrame(), pd.DataFrame())