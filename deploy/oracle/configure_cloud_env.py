from __future__ import annotations

import os
from pathlib import Path

from dotenv import set_key


def main() -> int:
    project_dir = Path(__file__).resolve().parents[2]
    env_path = project_dir / ".env"
    if not env_path.exists():
        raise SystemExit(".envがありません。Macで初回設定を完了してください。")

    settings = {
        "TAKEDA_CSV_PATH": str(project_dir / "data/latest.csv"),
        "TAKEDA_PROFILE_DIR": str(project_dir / ".takeda-profile"),
        "TAKEDA_AUTH_STATE": str(project_dir / ".takeda-auth.json"),
        "TAKEDA_BROWSER_CHANNEL": "chromium",
        # Xvfbの仮想画面上で通常のChromiumとして起動する。
        "TAKEDA_DOWNLOAD_HEADLESS": "false",
        "UPDATE_INTERVAL_MINUTES": "10",
    }
    for key, value in settings.items():
        set_key(str(env_path), key, value, quote_mode="never")

    os.chmod(env_path, 0o600)
    print("Oracle用ブラウザ設定へ切り替えました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
