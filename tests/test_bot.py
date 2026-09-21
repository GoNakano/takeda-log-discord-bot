import unittest
from datetime import datetime, timedelta

from bot import create_status_message


class BotStatusTest(unittest.TestCase):
    def test_recent_csv_is_healthy(self):
        now = datetime(2026, 7, 17, 12, 0)
        message = create_status_message(now - timedelta(minutes=10), now=now)

        self.assertIn("✅", message)
        self.assertIn("10分前", message)

    def test_stale_csv_is_reported(self):
        now = datetime(2026, 7, 17, 12, 0)
        message = create_status_message(now - timedelta(minutes=31), now=now)

        self.assertIn("⚠️", message)
        self.assertIn("31分前", message)


if __name__ == "__main__":
    unittest.main()
