import tarfile
import tempfile
import unittest
from pathlib import Path

from prepare_oracle_bundle import (
    _has_automatic_login_credentials,
    _secure_filter,
    _should_include,
)


class PrepareOracleBundleTest(unittest.TestCase):
    def test_excludes_csv_and_browser_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            csv_path = project_dir / "data/latest.csv"
            csv_path.parent.mkdir()
            csv_path.write_text("private", encoding="utf-8")
            profile_file = project_dir / ".takeda-profile/Preferences"
            profile_file.parent.mkdir()
            profile_file.write_text("private", encoding="utf-8")

            self.assertFalse(_should_include(csv_path, project_dir))
            self.assertFalse(_should_include(profile_file, project_dir))

    def test_excludes_os_unreliable_portable_auth_state(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            auth_path = project_dir / ".takeda-auth.json"
            auth_path.write_text("placeholder", encoding="utf-8")

            self.assertFalse(_should_include(auth_path, project_dir))

    def test_requires_automatic_login_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "TAKEDA_LOGIN_EMAIL='staff@example.com'\n"
                "TAKEDA_LOGIN_PASSWORD='secret'\n",
                encoding="utf-8",
            )

            self.assertTrue(_has_automatic_login_credentials(env_path))

    def test_secret_files_are_owner_only_inside_archive(self):
        tar_info = tarfile.TarInfo("takeda-log-discord-bot/.env")

        secured = _secure_filter(tar_info)

        self.assertEqual(secured.mode, 0o600)


if __name__ == "__main__":
    unittest.main()
