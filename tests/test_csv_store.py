import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from csv_store import EXPECTED_HEADERS, CsvFormatError, load_snapshot


class CsvStoreTest(unittest.TestCase):
    def _write_csv(self, rows, headers=EXPECTED_HEADERS) -> Path:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "sample.csv"
        with path.open("w", encoding="cp932", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)
            writer.writerows(rows)
        return path

    def test_loads_only_the_last_seven_days(self):
        path = self._write_csv(
            [
                [
                    "0000000001",
                    "テスト太郎",
                    "テストタロウ",
                    "2026/07/10 10:00",
                    "2026/07/10 12:30",
                    "150",
                ],
                [
                    "0000000001",
                    "テスト太郎",
                    "テストタロウ",
                    "2026/07/09 10:00",
                    "2026/07/09 11:00",
                    "60",
                ],
            ]
        )

        snapshot = load_snapshot(path, today=date(2026, 7, 16))

        self.assertEqual(len(snapshot.records), 1)
        self.assertEqual(snapshot.records[0].student_id, "0000000001")
        self.assertEqual(snapshot.records[0].duration_minutes, 150)

    def test_allows_missing_exit_time(self):
        path = self._write_csv(
            [
                [
                    "0000000002",
                    "テスト花子",
                    "テストハナコ",
                    "2026/07/16 18:00",
                    "",
                    "",
                ]
            ]
        )

        snapshot = load_snapshot(path, today=date(2026, 7, 16))

        self.assertIsNone(snapshot.records[0].exit_time)
        self.assertIsNone(snapshot.records[0].duration_minutes)

    def test_rejects_unexpected_headers(self):
        path = self._write_csv([], headers=("生徒番号", "生徒名"))

        with self.assertRaises(CsvFormatError):
            load_snapshot(path, today=date(2026, 7, 16))


if __name__ == "__main__":
    unittest.main()
