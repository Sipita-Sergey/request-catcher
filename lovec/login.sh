#!/usr/bin/env bash
# Обёртка для Mac/Linux: то же, что `python lovec/login.py code` / `password` (скрытый ввод).
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/../venv/bin/python"; [ -x "$PY" ] || PY="python3"
exec "$PY" "$HERE/login.py" "$@"
