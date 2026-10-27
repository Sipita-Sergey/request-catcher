#!/usr/bin/env bash
# Ввод кода из Телеграма и облачного пароля — скрыто, мимо чата и мимо агента.
#   ./login.sh code        спросит код и передаст его в login.py
#   ./login.sh password    спросит облачный пароль (если он у тебя включён)
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/../venv/bin/python"
[ -x "$PY" ] || PY="python3"

case "${1:-}" in
  code)
    read -r -s -p "Код из Телеграма (на экране ничего не появится), затем Enter: " V; echo
    RC=0; printf '%s' "$V" | "$PY" "$HERE/login.py" code || RC=$?
    ;;
  password)
    read -r -s -p "Облачный пароль Телеграма (на экране ничего не появится), затем Enter: " V; echo
    RC=0; printf '%s' "$V" | "$PY" "$HERE/login.py" password || RC=$?
    ;;
  *)
    echo "Использование: login.sh code | password"; exit 2 ;;
esac
unset V
exit ${RC:-0}
