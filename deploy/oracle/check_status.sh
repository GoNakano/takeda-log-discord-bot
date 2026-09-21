#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Bot: $(systemctl is-active takeda-log-bot.service || true)"
echo "CSV更新: $(systemctl is-active takeda-log-updater.service || true)"

if [[ -f "$PROJECT_DIR/.takeda-profile/.auth-required" ]]; then
    echo "Takeda-Log認証: 再ログインが必要"
else
    echo "Takeda-Log認証: 停止マーカーなし"
fi

"$PROJECT_DIR/.venv/bin/python" - "$PROJECT_DIR/data/latest.state.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    print("CSV状態: まだ取得されていません")
    raise SystemExit(0)

payload = json.loads(path.read_text(encoding="utf-8"))
print(f"CSV最終更新: {payload.get('updated_at', '不明')}")
print(f"CSV対象期間: {payload.get('date_from', '不明')}〜{payload.get('date_to', '不明')}")
PY
