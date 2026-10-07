from pathlib import Path
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def test_procfile_overrides_localhost_and_uses_heroku_port(self):
        procfile = (ROOT / "Procfile").read_text(encoding="utf-8").strip()
        process, command = procfile.split(":", 1)
        self.assertEqual(process, "web")
        arguments = shlex.split(command)
        self.assertEqual(arguments[:5], ["python", "-m", "streamlit", "run", "app.py"])
        self.assertIn("--server.address=0.0.0.0", arguments)
        self.assertIn("--server.port=$PORT", arguments)
        self.assertIn("--server.headless=true", arguments)
        config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["server"]["address"], "127.0.0.1")
        self.assertFalse(config["browser"]["gatherUsageStats"])
        self.assertNotEqual(config["server"].get("enableCORS"), False)
        self.assertNotEqual(config["server"].get("enableXsrfProtection"), False)

    def test_python_runtime_is_explicit(self):
        self.assertEqual((ROOT / ".python-version").read_text(encoding="utf-8").strip(), "3.14")

    @unittest.skipUnless(shutil.which("git"), "Requiere Git")
    def test_git_excludes_private_files_but_keeps_deployment_files(self):
        excluded = ["Archivos_Entrada/datos.csv", ".env", ".env.production", ".streamlit/secrets.toml", ".venv/pyvenv.cfg", ".vscode/settings.json", "descarga.xlsx", "descarga.csv"]
        included = ["app.py", "access.py", "requirements.txt", "Procfile", ".python-version", ".streamlit/config.toml", ".github/workflows/tests.yml"]
        with TemporaryDirectory() as folder:
            shutil.copyfile(ROOT / ".gitignore", Path(folder) / ".gitignore")
            subprocess.run(["git", "-C", folder, "init", "--quiet"], check=True, capture_output=True)
            result = subprocess.run(
                ["git", "-C", folder, "check-ignore", "--no-index", "--stdin", "-z"],
                input=("\0".join(excluded + included) + "\0").encode("utf-8"), capture_output=True, check=True,
            )
            self.assertEqual(set(result.stdout.decode("utf-8").strip("\0").split("\0")), set(excluded))


if __name__ == "__main__":
    unittest.main()