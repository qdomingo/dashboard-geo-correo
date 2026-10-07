import os
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'from access import require_access\nrequire_access()\nimport streamlit as st\nst.success("Autorizado")\n'


class AccessTests(unittest.TestCase):
    def test_local_without_password_still_works(self):
        with patch.dict(os.environ, {"APP_PASSWORD": "", "DYNO": ""}):
            app = AppTest.from_string(SOURCE).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.success), 1)

    def test_heroku_without_password_blocks_app(self):
        with patch.dict(os.environ, {"APP_PASSWORD": "", "DYNO": "web.1"}):
            app = AppTest.from_file(str(ROOT / "app.py")).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 1)
            self.assertEqual(len(app.get("file_uploader")), 0)

    def test_login_rejects_wrong_password_and_accepts_correct_password(self):
        with patch.dict(os.environ, {"DYNO": "web.1", "APP_PASSWORD": "test-only-password"}):
            app = AppTest.from_string(SOURCE).run()
            self.assertEqual(len(app.success), 0)
            app.text_input(key="access_password").set_value("wrong")
            app.button[0].click().run()
            self.assertEqual(len(app.success), 0)
            self.assertEqual(len(app.error), 1)
            app.text_input(key="access_password").set_value("test-only-password")
            app.button[0].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.success), 1)
            self.assertNotIn("access_password", app.session_state)

    def test_password_rotation_requires_new_login(self):
        with patch.dict(os.environ, {"APP_PASSWORD": "test-only-password"}):
            app = AppTest.from_string(SOURCE).run()
            app.text_input(key="access_password").set_value("test-only-password")
            app.button[0].click().run()
            self.assertEqual(len(app.success), 1)
            os.environ["APP_PASSWORD"] = "changed-test-password"
            app.run()
            self.assertEqual(len(app.success), 0)
            self.assertEqual(len(app.text_input), 1)


if __name__ == "__main__":
    unittest.main()