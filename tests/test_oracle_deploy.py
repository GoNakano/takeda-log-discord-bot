import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


class OracleDeployTest(unittest.TestCase):
    def test_installer_rejects_non_free_shape(self):
        script = (PROJECT_DIR / "deploy/oracle/install_on_vm.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn('shape != "VM.Standard.A1.Flex"', script)
        self.assertIn("ocpus > 1", script)
        self.assertIn("memory > 4", script)

    def test_updater_uses_virtual_display_and_loop_mode(self):
        unit = (
            PROJECT_DIR / "deploy/oracle/systemd/takeda-log-updater.service.in"
        ).read_text(encoding="utf-8")

        self.assertIn("xvfb-run", unit)
        self.assertIn("--loop", unit)
        self.assertIn("RestartPreventExitStatus=2", unit)

    def test_health_check_does_not_restart_after_auth_failure(self):
        script = (PROJECT_DIR / "deploy/oracle/health_check.sh.in").read_text(
            encoding="utf-8"
        )

        marker_position = script.index("AUTH_MARKER")
        updater_restart_position = script.index("restart takeda-log-updater.service")
        self.assertLess(marker_position, updater_restart_position)


if __name__ == "__main__":
    unittest.main()
