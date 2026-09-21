#!/usr/bin/env bash
set -Eeuo pipefail

ARCHIVE="${1:-takeda-log-bot-oracle.tar.gz}"
TARGET_DIR="$HOME/takeda-log-discord-bot"

if [[ ! -f "$ARCHIVE" ]]; then
    echo "Oracle転送ファイルが見つかりません。" >&2
    exit 1
fi
if [[ -e "$TARGET_DIR" ]]; then
    echo "既存の導入先があるため、安全のため上書きしません。" >&2
    exit 1
fi

mkdir -p "$TARGET_DIR"
chmod 700 "$TARGET_DIR"
tar -xzf "$ARCHIVE" -C "$TARGET_DIR" --strip-components=1
chmod +x "$TARGET_DIR/deploy/oracle/"*.sh
"$TARGET_DIR/deploy/oracle/install_on_vm.sh"

rm -f "$ARCHIVE"
echo "Oracle Always Freeへの導入が完了しました。"
