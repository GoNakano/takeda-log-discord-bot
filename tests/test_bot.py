import unittest
from datetime import datetime, timedelta

from bot import create_status_message, is_allowed_dm_user, is_allowed_guild, parse_ids


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


class GuildRestrictionTest(unittest.TestCase):
    def test_parse_comma_separated_ids(self):
        self.assertEqual(parse_ids(" 123, 456 ,,"), frozenset({123, 456}))

    def test_empty_value_means_no_restriction(self):
        self.assertEqual(parse_ids(""), frozenset())
        self.assertTrue(is_allowed_guild(999, frozenset()))
        self.assertTrue(is_allowed_guild(None, frozenset()))

    def test_invalid_id_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_ids("123,abc")

    def test_only_listed_guilds_are_allowed(self):
        allowed = frozenset({123})

        self.assertTrue(is_allowed_guild(123, allowed))
        self.assertFalse(is_allowed_guild(456, allowed))

    def test_direct_messages_are_rejected_when_restricted(self):
        self.assertFalse(is_allowed_guild(None, frozenset({123})))

    def test_listed_user_can_use_direct_message(self):
        self.assertTrue(is_allowed_dm_user(True, 42, frozenset({42})))

    def test_other_users_cannot_use_direct_message(self):
        self.assertFalse(is_allowed_dm_user(True, 7, frozenset({42})))
        self.assertFalse(is_allowed_dm_user(True, 7, frozenset()))

    def test_listed_user_outside_direct_message_is_not_exempted(self):
        # グループDMなど、1対1のDM以外では許可ユーザーでも例外にしない。
        self.assertFalse(is_allowed_dm_user(False, 42, frozenset({42})))


if __name__ == "__main__":
    unittest.main()
