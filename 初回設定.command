#!/bin/zsh
set -eu

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR"

if [[ ! -x .venv/bin/python ]]; then
    echo "Bot専用の実行環境がありません。"
    read "?Enterを押して閉じてください: "
    exit 1
fi

.venv/bin/python -m playwright install chromium
.venv/bin/python setup_config.py --overwrite
.venv/bin/python takeda_updater.py --login
.venv/bin/python takeda_updater.py --force

echo "初回設定とCSVの動作確認が完了しました。"
read "?Enterを押して閉じてください: "
