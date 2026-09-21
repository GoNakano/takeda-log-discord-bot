#!/usr/bin/env bash
set -u

BOT_STATE="$(systemctl is-active takeda-log-bot.service 2>/dev/null || true)"
TIMER_STATE="$(systemctl is-active takeda-log-updater.timer 2>/dev/null || true)"

echo "Discord Bot: $BOT_STATE"
echo "10分更新: $TIMER_STATE"

if [[ "$BOT_STATE" == "active" && "$TIMER_STATE" == "active" ]]; then
    echo "常時起動は正常です。Discordで /status を確認してください。"
    exit 0
fi

echo "常時起動を確認できません。" >&2
exit 1
