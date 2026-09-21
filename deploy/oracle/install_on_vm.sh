#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_USER="$(id -un)"
USER_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "aarch64" ]]; then
    echo "Oracle A1のUbuntu ARM64 VMではないため停止します。" >&2
    exit 1
fi
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    echo "Macで作成した転送ファイルではありません。" >&2
    exit 1
fi

METADATA_FILE="$(mktemp)"
trap 'rm -f "$METADATA_FILE"' EXIT
chmod 600 "$METADATA_FILE"
python3 - "$METADATA_FILE" <<'PY'
import sys
from urllib.request import Request, urlopen

request = Request(
    "http://169.254.169.254/opc/v2/instance/",
    headers={"Authorization": "Bearer Oracle"},
)
with urlopen(request, timeout=5) as response:
    payload = response.read()
with open(sys.argv[1], "wb") as handle:
    handle.write(payload)
PY

read -r SHAPE OCPUS MEMORY_GB < <(
    python3 - "$METADATA_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    metadata = json.load(handle)
shape_config = metadata.get("shapeConfig", {})
print(
    metadata.get("shape", ""),
    shape_config.get("ocpus", 999),
    shape_config.get("memoryInGBs", 999),
)
PY
)

python3 - "$SHAPE" "$OCPUS" "$MEMORY_GB" <<'PY'
import sys

shape, ocpus, memory = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
if shape != "VM.Standard.A1.Flex" or ocpus > 1 or memory > 4:
    raise SystemExit("無料固定条件（A1・1 OCPU・4GB以下）ではないため停止します。")
PY

echo "Oracle Always Free固定条件を確認しました。"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates \
    fonts-noto-cjk \
    python3 \
    python3-pip \
    python3-venv \
    xauth \
    xvfb

python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_DIR/.venv/bin/python" -m pip install -r "$PROJECT_DIR/requirements.txt"
sudo "$PROJECT_DIR/.venv/bin/python" -m playwright install-deps chromium
"$PROJECT_DIR/.venv/bin/python" -m playwright install chromium
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/deploy/oracle/configure_cloud_env.py"

chmod 600 "$PROJECT_DIR/.env"
if [[ -f "$PROJECT_DIR/.takeda-auth.json" ]]; then
    chmod 600 "$PROJECT_DIR/.takeda-auth.json"
fi
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

echo "Oracle上でCSV取得を1回テストします。"
/usr/bin/xvfb-run -a -s "-screen 0 1280x960x24 -nolisten tcp" \
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
        "$PROJECT_DIR/deploy/oracle/systemd/$UNIT.in" \
        | sudo tee "/etc/systemd/system/$UNIT" >/dev/null
done

sed \
    -e "s|__PROJECT_DIR__|$PROJECT_ESCAPED|g" \
    "$PROJECT_DIR/deploy/oracle/health_check.sh.in" \
    > "$PROJECT_DIR/deploy/oracle/health_check.sh"
chmod 700 "$PROJECT_DIR/deploy/oracle/health_check.sh"

sed \
    -e "s|__PROJECT_DIR__|$PROJECT_ESCAPED|g" \
    "$PROJECT_DIR/deploy/oracle/systemd/takeda-log-health.service.in" \
    | sudo tee /etc/systemd/system/takeda-log-health.service >/dev/null
sudo cp \
    "$PROJECT_DIR/deploy/oracle/systemd/takeda-log-health.timer" \
    /etc/systemd/system/takeda-log-health.timer

sudo systemctl daemon-reload
sudo systemctl enable --now takeda-log-bot.service
sudo systemctl enable --now takeda-log-updater.service
sudo systemctl enable --now takeda-log-health.timer

echo "Oracle常時起動設定が完了しました。"
"$PROJECT_DIR/deploy/oracle/check_status.sh"
