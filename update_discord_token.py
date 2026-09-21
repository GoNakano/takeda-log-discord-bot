from __future__ import annotations

import getpass
import os
from pathlib import Path

from dotenv import set_key


def _write_token(env_path: Path, token: str) -> None:
    set_key(str(env_path), "DISCORD_TOKEN", token, quote_mode="never")
    os.chmod(env_path, 0o600)


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    env_path = project_dir / ".env"
    if not env_path.is_file():
        print("先に初回設定.commandを実行してください。")
        return 1

    token = getpass.getpass(
        "再発行したDiscord Bot Token（画面には表示されません）: "
    ).strip()
    if not token:
        print("Tokenが空のため変更しませんでした。")
        return 1

    _write_token(env_path, token)

    runtime_env = Path.home() / "Library/Application Support/TakedaLogBot/.env"
    if runtime_env.is_file():
        _write_token(runtime_env, token)

    print("Discord Bot Tokenを設定用と常時起動用の両方へ安全に更新しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
