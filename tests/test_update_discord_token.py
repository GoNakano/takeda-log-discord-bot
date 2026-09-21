import tempfile
import unittest
from pathlib import Path

from dotenv import dotenv_values

from update_discord_token import _write_token


class UpdateDiscordTokenTest(unittest.TestCase):
    def test_writes_token_with_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("DISCORD_TOKEN=old\n", encoding="utf-8")

            _write_token(env_path, "new-token")

            self.assertEqual(dotenv_values(env_path)["DISCORD_TOKEN"], "new-token")
            self.assertEqual(env_path.stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
