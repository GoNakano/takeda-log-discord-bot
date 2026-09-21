#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_USER="$(id -un)"
USER_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "このファイルはGCEのLinux VM専用です。" >&2
    exit 1
fi

if [[ ! -f "$PROJECT_DIR/.env" || ! -f "$PROJECT_DIR/.takeda-auth.json" ]]; then
    echo "Macで初回設定を完了した転送ファイルではありません。" >&2
    exit 1
fi

echo "無料枠向けGCE環境を準備しています。"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv

python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_DIR/.venv/bin/python" -m pip install -r "$PROJECT_DIR/requirements.txt"
sudo "$PROJECT_DIR/.venv/bin/python" -m playwright install-deps chromium
"$PROJECT_DIR/.venv/bin/python" -m playwright install chromium
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/deploy/gce/configure_cloud_env.py"

chmod 600 "$PROJECT_DIR/.env" "$PROJECT_DIR/.takeda-auth.json"
mkdir -p \
    "$PROJECT_DIR/data" \
    "$PROJECT_DIR/logs" \
    "$PROJECT_DIR/.takeda-profile" \
    "$PROJECT_DIR/.runtime-home"
chmod 700 \
    "$PROJECT_DIR/data" \
    "$PROJECT_DIR/logs" \
    "$PROJECT_DIR/.takeda-profile" \
    "$PROJECT_DIR/.runtime-home"

sudo timedatectl set-timezone Asia/Tokyo

if ! sudo swapon --show=NAME --noheadings | grep -qx '/swapfile-takeda-log'; then
    sudo fallocate -l 1G /swapfile-takeda-log
    sudo chmod 600 /swapfile-takeda-log
    sudo mkswap /swapfile-takeda-log
    sudo swapon /swapfile-takeda-log
fi
if ! grep -q '^/swapfile-takeda-log ' /etc/fstab; then
    echo '/swapfile-takeda-log none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "GCE上でCSV取得を1回テストします。"
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/takeda_updater.py" --force

escape_sed() {
    printf '%s' "$1" | sed 's/[&|]/\\&/g'
}

PROJECT_ESCAPED="$(escape_sed "$PROJECT_DIR")"
USER_ESCAPED="$(escape_sed "$APP_USER")"
HOME_ESCAPED="$(escape_sed "$USER_HOME")"

for UNIT in takeda-log-bot.service takeda-log-updater.service; do
    sed \
        -e "s|__PROJECT_DIR__|$PROJECT_ESCAPED|g" \
        -e "s|__APP_USER__|$USER_ESCAPED|g" \
        -e "s|__USER_HOME__|$HOME_ESCAPED|g" \
        "$PROJECT_DIR/deploy/gce/systemd/$UNIT.in" \
        | sudo tee "/etc/systemd/system/$UNIT" >/dev/null
done
sudo cp \
    "$PROJECT_DIR/deploy/gce/systemd/takeda-log-updater.timer" \
    /etc/systemd/system/takeda-log-updater.timer

sudo systemctl daemon-reload
sudo systemctl enable --now takeda-log-bot.service
sudo systemctl enable --now takeda-log-updater.timer

echo "GCE常時起動設定が完了しました。"
"$PROJECT_DIR/deploy/gce/check_status.sh"
