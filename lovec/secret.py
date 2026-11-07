#!/usr/bin/env python3
"""Записывает секрет в data/.env скрытым вводом: значение не показывается на экране,
не попадает в историю команд и не проходит через агента. Работает в Windows, Mac и Linux.

  python lovec/secret.py TG_API_HASH
  python lovec/secret.py TG_BOT_TOKEN
  python lovec/secret.py LOVEC_API_KEY     ключ нейросети, если оценка идёт через API
"""
import getpass
import sys

import config

ALLOWED = ("TG_API_HASH", "TG_BOT_TOKEN", "LOVEC_API_KEY")


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in ALLOWED:
        print("⛔ эту команду используют только для %s. Несекретное агент пишет сам." % ", ".join(ALLOWED))
        return 2
    prompt = "Вставь значение для %s (на экране ничего не появится), затем Enter: " % name
    # не из терминала (тест, конвейер) — значение со stdin; в терминале — скрытый ввод
    value = (getpass.getpass(prompt) if sys.stdin.isatty() else sys.stdin.readline()).strip()
    if not value:
        print("⛔ пусто — ничего не записал")
        return 1
    config.set_value(name, value)
    del value
    print("✅ %s записан в data/.env" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
