#!/bin/zsh
set -eu

PROJECT_DIR="${0:A:h}"
RUNTIME_DIR="$HOME/Library/Application Support/TakedaLogBot"

if [[ ! -x "$RUNTIME_DIR/.venv/bin/python" ]]; then
    echo "常時起動用のBotがまだ設定されていません。"
    read "?Enterを押して閉じてください: "
    exit 1
fi

# 再ログイン前に、認証移行修正を含む最新版だけを実行用コピーへ反映する。
cp "$PROJECT_DIR/takeda_updater.py" "$RUNTIME_DIR/takeda_updater.py"
cp "$PROJECT_DIR/csv_store.py" "$RUNTIME_DIR/csv_store.py"
chmod 600 "$RUNTIME_DIR/takeda_updater.py" "$RUNTIME_DIR/csv_store.py"

cd "$RUNTIME_DIR"
"$RUNTIME_DIR/.venv/bin/python" takeda_updater.py --login
"$RUNTIME_DIR/.venv/bin/python" takeda_updater.py --force

# Oracle転送用のOS非依存認証JSONをDownloads側にも安全に戻す。
cp "$RUNTIME_DIR/.takeda-auth.json" "$PROJECT_DIR/.takeda-auth.json"
chmod 600 "$PROJECT_DIR/.takeda-auth.json"
rm -f "$PROJECT_DIR/.takeda-profile/.auth-required"

echo "Takeda-Logへの再ログインとCSV更新が完了しました。"
read "?Enterを押して閉じてください: "
