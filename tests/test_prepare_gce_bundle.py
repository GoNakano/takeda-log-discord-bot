import tarfile
import tempfile
import unittest
from pathlib import Path

from prepare_gce_bundle import _secure_filter, _should_include


class PrepareGceBundleTest(unittest.TestCase):
    def test_excludes_personal_csv_and_runtime_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            csv_path = project_dir / "data/latest.csv"
            csv_path.parent.mkdir()
            csv_path.write_text("private", encoding="utf-8")

            self.assertFalse(_should_include(csv_path, project_dir))

    def test_includes_required_secret_file_for_direct_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            env_path = project_dir / ".env"
            env_path.write_text("placeholder", encoding="utf-8")

            self.assertTrue(_should_include(env_path, project_dir))

    def test_secret_files_are_owner_only_inside_archive(self):
        tar_info = tarfile.TarInfo("takeda-log-discord-bot/.takeda-auth.json")

        secured = _secure_filter(tar_info)

        self.assertEqual(secured.mode, 0o600)


if __name__ == "__main__":
    unittest.main()
