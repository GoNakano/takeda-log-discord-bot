import unittest
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from takeda_updater import (
    AuthenticationRequired,
    _auth_required_marker,
    _automatic_login_credentials,
    _browser_channel,
    _clear_authentication_required,
    _date_cell_selector,
    _download_headless,
    _mark_authentication_required,
    _open_download_context,
    _profile_has_browser_state,
    _save_auth_state,
    _try_automatic_login,
    _update_interval_seconds,
    _within_update_window,
)


class TakedaUpdaterTest(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_automatic_login_is_optional_on_mac(self):
        self.assertIsNone(_automatic_login_credentials())

    @patch.dict("os.environ", {"TAKEDA_LOGIN_EMAIL": "staff@example.com"}, clear=True)
    def test_automatic_login_requires_both_values(self):
        with self.assertRaises(RuntimeError):
            _automatic_login_credentials()

    def test_date_selector_uses_zero_based_month(self):
        selector = _date_cell_selector(date(2026, 7, 16))

        self.assertIn('data-year="2026"', selector)
        self.assertIn('data-month="6"', selector)
        self.assertIn('data-date="16"', selector)

    @patch.dict("os.environ", {"UPDATE_START_HOUR": "10", "UPDATE_END_HOUR": "22"})
    def test_update_window(self):
        self.assertTrue(_within_update_window(datetime(2026, 7, 16, 10, 0)))
        self.assertTrue(_within_update_window(datetime(2026, 7, 16, 22, 0)))
        self.assertFalse(_within_update_window(datetime(2026, 7, 16, 9, 59)))
        self.assertFalse(_within_update_window(datetime(2026, 7, 16, 22, 1)))

    def test_authentication_failure_stops_future_attempts_until_login(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_dir = Path(directory) / "profile"

            _mark_authentication_required(profile_dir)
            self.assertTrue(_auth_required_marker(profile_dir).exists())

            _clear_authentication_required(profile_dir)
            self.assertFalse(_auth_required_marker(profile_dir).exists())

    def test_auth_state_includes_indexed_db_for_cloud_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            auth_state_path = Path(directory) / "auth.json"
            context = MagicMock()

            def write_state(*, path, indexed_db):
                self.assertTrue(indexed_db)
                Path(path).write_text('{"cookies": [], "origins": []}', encoding="utf-8")

            context.storage_state.side_effect = write_state

            _save_auth_state(context, auth_state_path)

            self.assertTrue(auth_state_path.is_file())
            context.storage_state.assert_called_once()

    @patch.dict("os.environ", {"TAKEDA_BROWSER_CHANNEL": "chromium"})
    def test_bundled_chromium_does_not_set_a_channel(self):
        self.assertIsNone(_browser_channel())

    @patch.dict("os.environ", {}, clear=True)
    def test_default_uses_bundled_chromium(self):
        self.assertIsNone(_browser_channel())

    @patch.dict("os.environ", {}, clear=True)
    def test_mac_download_opens_the_dedicated_browser_by_default(self):
        self.assertFalse(_download_headless())

    @patch.dict("os.environ", {"TAKEDA_BROWSER_CHANNEL": "chrome"})
    def test_mac_uses_installed_chrome_channel(self):
        self.assertEqual(_browser_channel(), "chrome")

    @patch.dict("os.environ", {"TAKEDA_BROWSER_CHANNEL": "chromium"})
    def test_download_reuses_the_dedicated_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_dir = Path(directory) / "profile"
            profile_dir.mkdir()
            (profile_dir / "Preferences").write_text("{}", encoding="utf-8")
            expected_context = MagicMock()
            playwright = MagicMock()
            playwright.chromium.launch_persistent_context.return_value = expected_context

            browser, context = _open_download_context(playwright, profile_dir)

            self.assertIsNone(browser)
            self.assertIs(context, expected_context)
            playwright.chromium.launch_persistent_context.assert_called_once()

    def test_empty_profile_is_not_treated_as_logged_in(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_dir = Path(directory) / "profile"
            profile_dir.mkdir()

            self.assertFalse(_profile_has_browser_state(profile_dir))

    @patch.dict("os.environ", {"TAKEDA_BROWSER_CHANNEL": "chromium"})
    def test_download_can_use_portable_auth_state(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_dir = Path(directory) / "profile"
            profile_dir.mkdir()
            auth_state_path = Path(directory) / "auth.json"
            auth_state_path.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
            expected_browser = MagicMock()
            expected_context = MagicMock()
            expected_browser.new_context.return_value = expected_context
            playwright = MagicMock()
            playwright.chromium.launch.return_value = expected_browser

            browser, context = _open_download_context(
                playwright,
                profile_dir,
                auth_state_path,
            )

            self.assertIs(browser, expected_browser)
            self.assertIs(context, expected_context)
            expected_browser.new_context.assert_called_once_with(
                storage_state=str(auth_state_path),
                accept_downloads=True,
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
            )

    @patch.dict(
        "os.environ",
        {
            "TAKEDA_BROWSER_CHANNEL": "chromium",
            "TAKEDA_LOGIN_EMAIL": "staff@example.com",
            "TAKEDA_LOGIN_PASSWORD": "secret",
        },
        clear=True,
    )
    def test_cloud_can_start_with_empty_browser_for_automatic_login(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_dir = Path(directory) / "profile"
            expected_browser = MagicMock()
            expected_context = MagicMock()
            expected_browser.new_context.return_value = expected_context
            playwright = MagicMock()
            playwright.chromium.launch.return_value = expected_browser

            browser, context = _open_download_context(
                playwright,
                profile_dir,
                Path(directory) / "missing-auth.json",
            )

            self.assertIs(browser, expected_browser)
            self.assertIs(context, expected_context)
            expected_browser.new_context.assert_called_once_with(
                accept_downloads=True,
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
            )

    @patch.dict(
        "os.environ",
        {
            "TAKEDA_LOGIN_EMAIL": "staff@example.com",
            "TAKEDA_LOGIN_PASSWORD": "secret",
        },
        clear=True,
    )
    def test_automatic_login_uses_staff_management_form_once(self):
        page = MagicMock()
        staff_button = MagicMock()
        staff_button.count.return_value = 1
        login_button = MagicMock()
        login_button.count.return_value = 1
        email_input = MagicMock()
        email_input.count.side_effect = [0, 1]
        password_input = MagicMock()
        password_input.count.return_value = 1
        period_input = MagicMock()

        page.get_by_role.side_effect = lambda _role, name, exact: {
            "校舎担当者": staff_button,
            "管理ログイン": login_button,
        }[name]
        page.get_by_placeholder.side_effect = lambda name, exact: {
            "メールアドレス": email_input,
            "パスワード": password_input,
            "期間を選択": period_input,
        }[name]

        self.assertTrue(_try_automatic_login(page, "https://example.com/history"))
        staff_button.click.assert_called_once()
        email_input.fill.assert_called_once_with("staff@example.com")
        password_input.fill.assert_called_once_with("secret")
        login_button.click.assert_called_once()
        page.goto.assert_called_once()

    @patch.dict(
        "os.environ",
        {
            "TAKEDA_LOGIN_EMAIL": "staff@example.com",
            "TAKEDA_LOGIN_PASSWORD": "wrong",
        },
        clear=True,
    )
    def test_failed_automatic_login_requests_stop(self):
        page = MagicMock()
        staff_button = MagicMock()
        staff_button.count.return_value = 0
        login_button = MagicMock()
        login_button.count.return_value = 1
        email_input = MagicMock()
        email_input.count.return_value = 1
        password_input = MagicMock()
        password_input.count.return_value = 1
        period_input = MagicMock()
        period_input.wait_for.side_effect = RuntimeError("not logged in")

        page.get_by_role.side_effect = lambda _role, name, exact: {
            "校舎担当者": staff_button,
            "管理ログイン": login_button,
        }[name]
        page.get_by_placeholder.side_effect = lambda name, exact: {
            "メールアドレス": email_input,
            "パスワード": password_input,
            "期間を選択": period_input,
        }[name]

        with self.assertRaises(AuthenticationRequired):
            _try_automatic_login(page, "https://example.com/history")
        login_button.click.assert_called_once()

    @patch.dict("os.environ", {"UPDATE_INTERVAL_MINUTES": "10"})
    def test_update_interval(self):
        self.assertEqual(_update_interval_seconds(), 600)

    @patch.dict("os.environ", {"UPDATE_INTERVAL_MINUTES": "1"})
    def test_update_interval_rejects_excessive_access(self):
        with self.assertRaises(RuntimeError):
            _update_interval_seconds()


if __name__ == "__main__":
    unittest.main()
