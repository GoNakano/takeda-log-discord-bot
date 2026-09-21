from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
from urllib.parse import urlparse


DEFAULTS = {
    "TAKEDA_CSV_PATH": "data/latest.csv",
    "TAKEDA_PROFILE_DIR": ".takeda-profile",
    "TAKEDA_AUTH_STATE": ".takeda-auth.json",
    "TAKEDA_BROWSER_CHANNEL": "chromium",
    "TAKEDA_DOWNLOAD_HEADLESS": "false",
    "UPDATE_START_HOUR": "10",
    "UPDATE_END_HOUR": "22",
    "UPDATE_INTERVAL_MINUTES": "10",
    "TAKEDA_LOGIN_EMAIL": "",
    "TAKEDA_LOGIN_PASSWORD": "",
}


def _valid_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Botの秘密設定をこのMacだけに保存します。")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="既存の.envを置き換える",
    )
    args = parser.parse_args()

    env_path = Path(".env").resolve()
    if env_path.exists() and not args.overwrite:
        print(".envは既にあります。変更する場合は--overwriteを付けてください。")
        return 1

    print("入力内容は.envだけに保存され、GitHubの対象外です。")
    discord_token = getpass.getpass("Discord Bot Token（画面には表示されません）: ").strip()
    history_url = getpass.getpass(
        "Takeda-Logの登下校履歴画面URL（画面には表示されません）: "
    ).strip()

    if not discord_token:
        print("Discord Bot Tokenが空です。")
        return 1
    if not _valid_https_url(history_url):
        print("Takeda-LogのURLはhttps://から始まるURLを入力してください。")
        return 1

    lines = [
        f"DISCORD_TOKEN={discord_token}",
        f"TAKEDA_HISTORY_URL={history_url}",
        *(f"{key}={value}" for key, value in DEFAULTS.items()),
    ]
    temporary_path = env_path.with_suffix(".tmp")
    temporary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, env_path)
    print("設定をこのMacへ保存しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
