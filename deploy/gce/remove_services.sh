#!/usr/bin/env bash
set -Eeuo pipefail

sudo systemctl disable --now takeda-log-bot.service 2>/dev/null || true
sudo systemctl disable --now takeda-log-updater.timer 2>/dev/null || true
sudo rm -f \
    /etc/systemd/system/takeda-log-bot.service \
    /etc/systemd/system/takeda-log-updater.service \
    /etc/systemd/system/takeda-log-updater.timer
sudo systemctl daemon-reload

echo "常時起動だけを解除しました。コードと秘密ファイルは削除していません。"
