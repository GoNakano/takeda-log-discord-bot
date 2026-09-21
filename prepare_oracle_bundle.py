from __future__ import annotations

import argparse
import os
import shutil
import tarfile
from pathlib import Path

from dotenv import dotenv_values


EXCLUDED_PARTS = {
    ".venv",
    ".takeda-profile",
    "__pycache__",
    "data",
    "dist",
    "logs",
}
EXCLUDED_SUFFIXES = {".csv", ".log", ".pyc", ".state.json"}
EXCLUDED_FILENAMES = {".takeda-auth.json"}
REQUIRED_SECRET_FILES = (".env",)


def _should_include(path: Path, project_dir: Path) -> bool:
    relative_path = path.relative_to(project_dir)
    if any(part in EXCLUDED_PARTS for part in relative_path.parts):
        return False
    if path.name in EXCLUDED_FILENAMES:
        return False
    if any(path.name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return False
    return path.is_file()


def _secure_filter(tar_info: tarfile.TarInfo) -> tarfile.TarInfo:
    if tar_info.name.endswith("/.env"):
        tar_info.mode = 0o600
    elif tar_info.name.endswith((".sh", ".command")):
        tar_info.mode = 0o700
    else:
        tar_info.mode = 0o600
    tar_info.uid = 0
    tar_info.gid = 0
    tar_info.uname = ""
    tar_info.gname = ""
    return tar_info


def _has_automatic_login_credentials(env_path: Path) -> bool:
    values = dotenv_values(env_path)
    email = (values.get("TAKEDA_LOGIN_EMAIL") or "").strip()
    password = values.get("TAKEDA_LOGIN_PASSWORD") or ""
    return bool(email and password)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Oracle Always Freeへ安全に転送するファイルを作ります。"
    )
    parser.add_argument(
        "--token-rotated",
        action="store_true",
        help="過去に画面へ表示したDiscord Tokenを再発行済みであることを確認する",
    )
    args = parser.parse_args()

    if not args.token_rotated:
        print(
            "安全のため処理を停止しました。Discord Tokenを再発行してから、"
            "--token-rotatedを付けて実行してください。"
        )
        return 1

    project_dir = Path(__file__).resolve().parent
    missing = [name for name in REQUIRED_SECRET_FILES if not (project_dir / name).is_file()]
    if missing:
        print("初回設定が完了していません。")
        return 1
    if not _has_automatic_login_credentials(project_dir / ".env"):
        print("先にTakeda-Log自動ログイン設定.commandを実行してください。")
        return 1

    output_dir = project_dir / "dist"
    output_dir.mkdir(mode=0o700, exist_ok=True)
    output_path = output_dir / "takeda-log-bot-oracle.tar.gz"

    with tarfile.open(output_path, "w:gz") as archive:
        for path in sorted(project_dir.rglob("*")):
            if not _should_include(path, project_dir):
                continue
            relative_path = path.relative_to(project_dir)
            archive.add(
                path,
                arcname=Path("takeda-log-discord-bot") / relative_path,
                recursive=False,
                filter=_secure_filter,
            )

    os.chmod(output_path, 0o600)
    install_script = output_dir / "install_on_oracle.sh"
    shutil.copy2(
        project_dir / "deploy/oracle/deploy_archive.sh",
        install_script,
    )
    os.chmod(install_script, 0o700)

    print("Oracle転送ファイルを作成しました。")
    print("distフォルダ内の2ファイルは秘密情報を含むためGitHubへ置かないでください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
