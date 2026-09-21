from __future__ import annotations

import getpass
import os
from pathlib import Path

from dotenv import set_key


def _write_credentials(env_path: Path, email: str, password: str) -> None:
    set_key(str(env_path), "TAKEDA_LOGIN_EMAIL", email, quote_mode="always")
    set_key(str(env_path), "TAKEDA_LOGIN_PASSWORD", password, quote_mode="always")
    os.chmod(env_path, 0o600)


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    env_path = project_dir / ".env"
    if not env_path.is_file():
        print("先に初回設定.commandを実行してください。")
        return 1

    email = getpass.getpass(
        "Takeda-Logの校舎担当者メールアドレス（画面には表示されません）: "
    ).strip()
    password = getpass.getpass(
        "Takeda-Logの校舎担当者パスワード（画面には表示されません）: "
    )
    if not email or not password:
        print("メールアドレスまたはパスワードが空のため変更しませんでした。")
        return 1
    if "\n" in email or "\r" in email or "\n" in password or "\r" in password:
        print("改行を含む認証情報は保存できません。")
        return 1

    _write_credentials(env_path, email, password)

    runtime_env = (
        Path.home() / "Library/Application Support/TakedaLogBot/.env"
    )
    if runtime_env.is_file():
        _write_credentials(runtime_env, email, password)

    print("Takeda-Logの自動ログイン情報をこのMacだけに保存しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
