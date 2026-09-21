#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "先に初回設定.commandを実行してください。"
  read -r "?Enterを押すと閉じます: "
  exit 1
fi

".venv/bin/python" update_discord_token.py
read -r "?Enterを押すと閉じます: "
