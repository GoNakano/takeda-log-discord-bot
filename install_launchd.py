from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


LABELS = (
    "com.gonakano.takeda-log-bot",
    "com.gonakano.takeda-log-updater",
)
RUNTIME_DIR = Path.home() / "Library/Application Support/TakedaLogBot"


def _runtime_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = {".git", ".DS_Store", "__pycache__", "dist", "logs"}
    ignored.update(name for name in names if name.endswith(".pyc"))
    ignored.update(name for name in names if name.startswith("Singleton"))
    return ignored.intersection(names)


def _copy_runtime(source_dir: Path, runtime_dir: Path) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copytree(
        source_dir,
        runtime_dir,
        dirs_exist_ok=True,
        symlinks=True,
        ignore=_runtime_ignore,
    )
    os.chmod(runtime_dir, 0o700)

    for directory in (
        runtime_dir / ".takeda-profile",
        runtime_dir / "data",
        runtime_dir / "logs",
    ):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)

    for secret_file in (
        runtime_dir / ".env",
        runtime_dir / ".takeda-auth.json",
        runtime_dir / "data/latest.csv",
        runtime_dir / "data/latest.state.json",
    ):
        if secret_file.exists():
            os.chmod(secret_file, 0o600)


def _replace_project_dir(value, project_dir: Path):
    if isinstance(value, str):
        return value.replace("__PROJECT_DIR__", str(project_dir))
    if isinstance(value, list):
        return [_replace_project_dir(item, project_dir) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_project_dir(item, project_dir)
            for key, item in value.items()
        }
    return value


def _run_launchctl(*arguments: str, check: bool = True) -> None:
    subprocess.run(
        ["/bin/launchctl", *arguments],
        check=check,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _remove(launch_agents: Path) -> None:
    domain = f"gui/{os.getuid()}"
    for label in LABELS:
        destination = launch_agents / f"{label}.plist"
        _run_launchctl("bootout", domain, str(destination), check=False)
        destination.unlink(missing_ok=True)
    print("BotとCSV更新の常時起動を解除しました。")


def _install(project_dir: Path, launch_agents: Path) -> None:
    required_paths = (
        project_dir / ".env",
        project_dir / ".venv/bin/python",
        project_dir / ".takeda-auth.json",
        project_dir / ".takeda-profile",
        project_dir / "data/latest.csv",
    )
    if any(not path.exists() for path in required_paths):
        raise RuntimeError(
            "初回設定とCSVの1回取得が完了していません。先に「初回設定.command」を実行してください。"
        )

    launch_agents.mkdir(parents=True, exist_ok=True)
    domain = f"gui/{os.getuid()}"

    # DownloadsはバックグラウンドPythonからの参照がmacOSに止められるため、
    # 既存ジョブを先に止め、ユーザー専用のApplication Supportへ実行用コピーを置く。
    for label in LABELS:
        destination = launch_agents / f"{label}.plist"
        _run_launchctl("bootout", domain, str(destination), check=False)

    _copy_runtime(project_dir, RUNTIME_DIR)

    for label in LABELS:
        template = RUNTIME_DIR / "launchd" / f"{label}.plist.example"
        destination = launch_agents / f"{label}.plist"
        with template.open("rb") as template_file:
            configuration = plistlib.load(template_file)
        configuration = _replace_project_dir(configuration, RUNTIME_DIR)

        temporary_path = destination.with_suffix(".tmp")
        with temporary_path.open("wb") as temporary_file:
            plistlib.dump(configuration, temporary_file, sort_keys=False)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, destination)

        _run_launchctl("bootstrap", domain, str(destination))

    print(
        "Botを常時起動し、CSVを10分ごとに更新する設定を有効にしました。"
        "実行用データはMacのApplication Supportへ安全に保存しています。"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Macの常時起動設定を管理します。")
    parser.add_argument("--remove", action="store_true", help="常時起動設定を解除する")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    launch_agents = Path.home() / "Library/LaunchAgents"

    try:
        if args.remove:
            _remove(launch_agents)
        else:
            _install(project_dir, launch_agents)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"常時起動設定に失敗しました: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
