#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
RUNTIME_DIR="$HOME/Library/Application Support/TakedaLogBot"
cd "$SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "先に初回設定.commandを実行してください。"
  read -r "?Enterを押すと閉じます: "
  exit 1
fi

".venv/bin/python" update_takeda_credentials.py

# Macの既存ログイン状態を使わず、自動ログインだけで取得できるか1回確認する。
TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/takeda-auto-login.XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT
env \
  TAKEDA_PROFILE_DIR="$TEST_DIR/profile" \
  TAKEDA_AUTH_STATE="$TEST_DIR/auth.json" \
  TAKEDA_CSV_PATH="$TEST_DIR/latest.csv" \
  TAKEDA_BROWSER_CHANNEL="chromium" \
  TAKEDA_DOWNLOAD_HEADLESS="false" \
  ".venv/bin/python" takeda_updater.py --force

if [[ -d "$RUNTIME_DIR" ]]; then
  cp "$SCRIPT_DIR/takeda_updater.py" "$RUNTIME_DIR/takeda_updater.py"
  cp "$SCRIPT_DIR/csv_store.py" "$RUNTIME_DIR/csv_store.py"
  chmod 600 "$RUNTIME_DIR/takeda_updater.py" "$RUNTIME_DIR/csv_store.py"
fi

echo "自動ログインの動作確認が完了しました。"
read -r "?Enterを押すと閉じます: "
