#!/usr/bin/env bash
# Обёртка для Mac/Linux: то же, что `python lovec/secret.py ИМЯ` (скрытый ввод мимо агента).
#   ./set-secret.sh TG_API_HASH | TG_BOT_TOKEN | LOVEC_API_KEY
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/../venv/bin/python"; [ -x "$PY" ] || PY="python3"
exec "$PY" "$HERE/secret.py" "$@"
