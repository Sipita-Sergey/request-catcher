#!/usr/bin/env bash
# Обёртка для Mac/Linux: то же, что `python3 setup.py` (он работает и на Windows).
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo "⛔ нет python3. Поставь Python 3.9 или новее и запусти ещё раз."; exit 1; }
python3 "$HERE/setup.py"
chmod +x "$HERE"/lovec/*.sh "$HERE"/lovec/*.py 2>/dev/null || true
