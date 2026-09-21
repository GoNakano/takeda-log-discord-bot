from __future__ import annotations

import os
import shutil
import tarfile
from pathlib import Path


EXCLUDED_PARTS = {
    ".venv",
    ".takeda-profile",
    "__pycache__",
    "data",
    "dist",
    "logs",
}
EXCLUDED_SUFFIXES = {".csv", ".log", ".pyc", ".state.json"}
REQUIRED_SECRET_FILES = (".env", ".takeda-auth.json")


def _should_include(path: Path, project_dir: Path) -> bool:
    relative_path = path.relative_to(project_dir)
    if any(part in EXCLUDED_PARTS for part in relative_path.parts):
        return False
    if any(path.name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return False
    return path.is_file()


def _secure_filter(tar_info: tarfile.TarInfo) -> tarfile.TarInfo:
    if tar_info.name.endswith(("/.env", "/.takeda-auth.json")):
        tar_info.mode = 0o600
    elif tar_info.name.endswith(".sh"):
        tar_info.mode = 0o700
    else:
        tar_info.mode = 0o600
    tar_info.uid = 0
    tar_info.gid = 0
    tar_info.uname = ""
    tar_info.gname = ""
    return tar_info


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    missing = [name for name in REQUIRED_SECRET_FILES if not (project_dir / name).is_file()]
    if missing:
        print("初回設定が未完了です。先に初回設定.commandを実行してください。")
        return 1

    output_dir = project_dir / "dist"
    output_dir.mkdir(mode=0o700, exist_ok=True)
    output_path = output_dir / "takeda-log-bot-gce.tar.gz"

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
    cloud_shell_script = output_dir / "deploy_from_cloud_shell.sh"
    shutil.copy2(
        project_dir / "deploy/gce/deploy_from_cloud_shell.sh",
        cloud_shell_script,
    )
    os.chmod(cloud_shell_script, 0o700)
    print(f"GCE転送ファイルを作成しました: {output_path}")
    print(f"Cloud Shell用スクリプト: {cloud_shell_script}")
    print("このファイルはTokenとログイン情報を含むため、GitHubへ置かないでください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
