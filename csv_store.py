from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


EXPECTED_HEADERS = (
    "生徒番号",
    "生徒名",
    "生徒名カナ",
    "登校時間",
    "下校時間",
    "学習時間",
)

DATETIME_FORMATS = (
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
)


class CsvFormatError(ValueError):
    """Takeda-LogのCSV形式が想定と異なる場合に送出する。"""


@dataclass(frozen=True)
class AttendanceRecord:
    student_id: str
    student_name: str
    student_name_kana: str
    entrance_time: datetime
    exit_time: datetime | None

    @property
    def duration_minutes(self) -> int | None:
        if self.exit_time is None:
            return None

        minutes = int((self.exit_time - self.entrance_time).total_seconds() // 60)
        return max(minutes, 0)


@dataclass(frozen=True)
class AttendanceSnapshot:
    records: tuple[AttendanceRecord, ...]
    updated_at: datetime
    source_path: Path

    @property
    def student_map(self) -> dict[str, str]:
        students: dict[str, str] = {}
        for record in self.records:
            students[record.student_id] = record.student_name
        return students


def _decode_csv(path: Path) -> str:
    raw = path.read_bytes()

    # Takeda-LogのCSVはShift_JIS系。将来UTF-8へ変わっても読めるようにする。
    for encoding in ("cp932", "utf-8-sig"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise CsvFormatError("CSVの文字コードを判定できませんでした。")


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    value = value.strip()
    for datetime_format in DATETIME_FORMATS:
        try:
            return datetime.strptime(value, datetime_format)
        except ValueError:
            continue

    raise CsvFormatError(f"{field_name}の日時形式が想定と異なります。")


def _parse_optional_datetime(value: str, *, field_name: str) -> datetime | None:
    if not value.strip():
        return None
    return _parse_datetime(value, field_name=field_name)


def load_snapshot(
    path: str | os.PathLike[str],
    *,
    today: date | None = None,
    days: int = 7,
) -> AttendanceSnapshot:
    """CSVを読み込み、今日を含む直近`days`日だけを返す。"""

    source_path = Path(path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if days < 1:
        raise ValueError("daysは1以上で指定してください。")

    text = _decode_csv(source_path)
    rows = csv.DictReader(text.splitlines())
    headers = tuple((rows.fieldnames or []))
    if headers != EXPECTED_HEADERS:
        raise CsvFormatError("CSVの列名または列順が想定と異なります。")

    reference_date = today or date.today()
    date_from = reference_date - timedelta(days=days - 1)
    records: list[AttendanceRecord] = []

    for line_number, row in enumerate(rows, start=2):
        student_id = (row.get("生徒番号") or "").strip()
        student_name = (row.get("生徒名") or "").strip()
        if not student_id or not student_name:
            raise CsvFormatError(f"{line_number}行目の生徒情報が不足しています。")

        entrance_time = _parse_datetime(
            row.get("登校時間") or "",
            field_name=f"{line_number}行目の登校時間",
        )
        exit_time = _parse_optional_datetime(
            row.get("下校時間") or "",
            field_name=f"{line_number}行目の下校時間",
        )

        if exit_time is not None and exit_time < entrance_time:
            raise CsvFormatError(f"{line_number}行目の下校時間が登校時間より前です。")

        if date_from <= entrance_time.date() <= reference_date:
            records.append(
                AttendanceRecord(
                    student_id=student_id,
                    student_name=student_name,
                    student_name_kana=(row.get("生徒名カナ") or "").strip(),
                    entrance_time=entrance_time,
                    exit_time=exit_time,
                )
            )

    records.sort(key=lambda record: record.entrance_time)
    updated_at = datetime.fromtimestamp(source_path.stat().st_mtime)
    return AttendanceSnapshot(
        records=tuple(records),
        updated_at=updated_at,
        source_path=source_path,
    )
