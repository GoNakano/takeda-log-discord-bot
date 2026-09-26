#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "先に初回設定.commandを実行してください。"
  read -r "?Enterを押すと閉じます: "
  exit 1
fi

echo "転送ファイルには、Developer Portalで再発行した新しいDiscord Bot Tokenを入れます。"
read -r "ANSWER?Tokenを再発行して保存済みなら YES と入力してください: "
if [[ "$ANSWER" != "YES" ]]; then
  echo "安全のため中止しました。"
  read -r "?Enterを押すと閉じます: "
  exit 1
fi

".venv/bin/python" prepare_oracle_bundle.py --token-rotated
echo "完了しました。distフォルダを確認してください。"
read -r "?Enterを押すと閉じます: "
