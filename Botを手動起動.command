#!/bin/zsh
set -eu

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR"
mkdir -p logs

echo "Discord Botを起動します。この確認中は画面を閉じないでください。"
exec .venv/bin/python bot.py
