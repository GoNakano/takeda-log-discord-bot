#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR"
.venv/bin/python install_launchd.py
RESULT=$?

read "?Enterを押して閉じてください: "
exit $RESULT
