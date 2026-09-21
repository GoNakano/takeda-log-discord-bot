#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "先に初回設定.commandを実行してください。"
  read -r "?Enterを押すと閉じます: "
  exit 1
fi

echo "以前チャットへ貼ったDiscord Bot Tokenは無効化し、新しいTokenへ入れ替えましたか？"
read -r "ANSWER?再発行済みなら YES と入力してください: "
if [[ "$ANSWER" != "YES" ]]; then
  echo "安全のため中止しました。"
  read -r "?Enterを押すと閉じます: "
  exit 1
fi

".venv/bin/python" prepare_oracle_bundle.py --token-rotated
echo "完了しました。distフォルダを確認してください。"
read -r "?Enterを押すと閉じます: "
