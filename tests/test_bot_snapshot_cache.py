import asyncio
import csv
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import bot
from bot import SnapshotCache
from csv_store import EXPECTED_HEADERS, load_snapshot


def _row(day: str) -> list:
    return ["0000000001", "テスト太郎", "テストタロウ", f"{day} 10:00", f"{day} 11:00", "60"]


class SnapshotCacheTest(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.path = Path(temporary_directory.name) / "latest.csv"
        # 今日の記録を入れておき、直近7日の絞り込みで消えないようにする。
        self.today = date.today()
        self._write([_row(self.today.strftime("%Y/%m/%d"))])

    def _write(self, rows) -> None:
        with self.path.open("w", encoding="cp932", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(EXPECTED_HEADERS)
            writer.writerows(rows)

    def test_reuses_result_while_file_is_unchanged(self):
        cache = SnapshotCache(self.path)
        with mock.patch("bot.load_snapshot", wraps=load_snapshot) as loader:
            first = cache.load()
            second = cache.load()

        self.assertIs(first, second)
        self.assertEqual(loader.call_count, 1)

    def test_reloads_after_file_is_replaced(self):
        cache = SnapshotCache(self.path)
        first = cache.load()

        day = self.today.strftime("%Y/%m/%d")
        self._write([_row(day), _row(day)])
        # 同じ秒内の書き換えでも確実に変化を検出できるよう、更新時刻もずらす。
        stat = self.path.stat()
        os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

        second = cache.load()
        self.assertEqual(len(first.records), 1)
        self.assertEqual(len(second.records), 2)

    def test_reloads_when_date_changes(self):
        cache = SnapshotCache(self.path)
        tomorrow = date.fromordinal(self.today.toordinal() + 1)

        class FakeDate(date):
            @classmethod
            def today(cls):
                return tomorrow

        with mock.patch("bot.load_snapshot", wraps=load_snapshot) as loader:
            cache.load()
            with mock.patch("bot.date", FakeDate):
                cache.load()

        self.assertEqual(loader.call_count, 2)

    def test_missing_file_raises(self):
        cache = SnapshotCache(self.path.with_name("missing.csv"))
        with self.assertRaises(FileNotFoundError):
            cache.load()

    def test_load_async_returns_same_snapshot(self):
        cache = SnapshotCache(self.path)
        snapshot = asyncio.run(cache.load_async())
        self.assertIs(snapshot, cache.load())


class StatusCommandTest(unittest.TestCase):
    def test_status_defers_before_reading_csv(self):
        calls = []
        interaction = mock.MagicMock()
        interaction.response.defer = mock.AsyncMock(
            side_effect=lambda **kwargs: calls.append("defer")
        )
        interaction.followup.send = mock.AsyncMock()

        async def fake_load():
            calls.append("load")
            raise FileNotFoundError

        with mock.patch.object(bot.snapshot_cache, "load_async", fake_load):
            asyncio.run(bot.status.callback(interaction))

        self.assertEqual(calls, ["defer", "load"])
        interaction.response.defer.assert_awaited_once_with(thinking=True, ephemeral=True)
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("CSVはまだ取得されていません", message)
        self.assertTrue(interaction.followup.send.await_args.kwargs["ephemeral"])


if __name__ == "__main__":
    unittest.main()
