import unittest
import tempfile
from pathlib import Path

from install_launchd import _copy_runtime, _replace_project_dir


class InstallLaunchdTest(unittest.TestCase):
    def test_replaces_project_directory_recursively(self):
        value = {
            "WorkingDirectory": "__PROJECT_DIR__",
            "ProgramArguments": ["__PROJECT_DIR__/.venv/bin/python", "bot.py"],
            "RunAtLoad": True,
        }

        replaced = _replace_project_dir(value, Path("/tmp/sample"))

        self.assertEqual(replaced["WorkingDirectory"], "/tmp/sample")
        self.assertEqual(
            replaced["ProgramArguments"][0],
            "/tmp/sample/.venv/bin/python",
        )
        self.assertTrue(replaced["RunAtLoad"])

    def test_copies_runtime_without_logs_or_browser_locks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            runtime = root / "runtime"
            (source / ".takeda-profile").mkdir(parents=True)
            (source / "data").mkdir()
            (source / "logs").mkdir()
            (source / "bot.py").write_text("print('ok')\n", encoding="utf-8")
            (source / ".env").write_text("SECRET=value\n", encoding="utf-8")
            (source / ".takeda-auth.json").write_text("{}\n", encoding="utf-8")
            (source / "data/latest.csv").write_text("sample\n", encoding="utf-8")
            (source / "logs/bot.log").write_text("old\n", encoding="utf-8")
            (source / ".takeda-profile/SingletonLock").write_text(
                "locked\n", encoding="utf-8"
            )

            _copy_runtime(source, runtime)

            self.assertTrue((runtime / "bot.py").exists())
            self.assertTrue((runtime / "data/latest.csv").exists())
            self.assertFalse((runtime / "logs/bot.log").exists())
            self.assertFalse((runtime / ".takeda-profile/SingletonLock").exists())
            self.assertEqual((runtime / ".env").stat().st_mode & 0o777, 0o600)
            self.assertEqual(runtime.stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
