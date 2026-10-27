#!/usr/bin/env bash
# Установка ловца: окружение + пустые заготовки в data/. Безопасно запускать повторно.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

if ! command -v python3 >/dev/null 2>&1; then
  echo "⛔ нет python3. Поставь Python 3.9 или новее и запусти ещё раз."; exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "⛔ Python старше 3.9 ($(python3 -V)). Нужен 3.9 или новее."; exit 1
fi

if [ ! -x venv/bin/python ]; then
  python3 -m venv venv || { echo "⛔ не создалось окружение. На Debian/Ubuntu: sudo apt install python3-venv"; exit 1; }
fi
venv/bin/pip install -q --upgrade pip >/dev/null
venv/bin/pip install -q -r requirements.txt
echo "✅ окружение и зависимости готовы"

mkdir -p data
[ -f data/niche.md ]   || cp templates/niche.md data/niche.md
[ -f data/phrases.txt ] || cp templates/phrases.example.txt data/phrases.txt
[ -f data/.env ]       || { touch data/.env; chmod 600 data/.env; }
chmod +x lovec/*.sh lovec/*.py 2>/dev/null || true
echo "✅ заготовки в data/ созданы (ниша, фразы, настройки) — это твои файлы, в git они не попадают"
