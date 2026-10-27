#!/usr/bin/env bash
# Записывает секрет в data/.env скрытым вводом: значение не показывается на экране,
# не попадает в историю команд и не проходит через агента.
#   ./set-secret.sh TG_API_HASH
#   ./set-secret.sh TG_BOT_TOKEN
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ENVF="$HERE/../data/.env"
NAME="${1:-}"
case "$NAME" in
  TG_API_HASH|TG_BOT_TOKEN) ;;
  *) echo "⛔ эту команду используют только для TG_API_HASH и TG_BOT_TOKEN. Несекретное агент пишет сам."; exit 2 ;;
esac

mkdir -p "$HERE/../data"; touch "$ENVF"; chmod 600 "$ENVF"
read -r -s -p "Вставь значение для $NAME (на экране ничего не появится), затем Enter: " V; echo
if [ -z "$V" ]; then echo "⛔ пусто — ничего не записал"; exit 1; fi
grep -v "^${NAME}=" "$ENVF" > "$ENVF.tmp" || true
printf '%s=%s\n' "$NAME" "$V" >> "$ENVF.tmp"
mv "$ENVF.tmp" "$ENVF"; chmod 600 "$ENVF"
unset V
echo "✅ $NAME записан в data/.env"
