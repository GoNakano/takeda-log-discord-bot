from __future__ import annotations

import os
from pathlib import Path

from dotenv import set_key


def main() -> int:
    project_dir = Path(__file__).resolve().parents[2]
    env_path = project_dir / ".env"
    if not env_path.exists():
        raise SystemExit(".envがありません。Macで初回設定を完了してください。")

    set_key(str(env_path), "TAKEDA_BROWSER_CHANNEL", "chromium", quote_mode="never")
    os.chmod(env_path, 0o600)
    print("GCE用ブラウザ設定へ切り替えました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
