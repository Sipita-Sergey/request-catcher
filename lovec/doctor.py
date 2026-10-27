#!/usr/bin/env python3
"""Проверка готовности ловца по шагам. По ней онбординг понимает, где остановился:
первый красный пункт — следующий шаг. Ничего не меняет и секретов не печатает.

  doctor.py          таблица
  doctor.py --json   то же машинно (для агента)
  doctor.py --offline  без обращений в Телеграм
"""
import json
from pathlib import Path
import subprocess
import sys

import config
import db
import schedule as sched

PLACEHOLDER = "<<ЗАПОЛНИТЬ"


def check(offline):
    items = []

    def add(key, title, ok, who, hint, detail=""):
        items.append({"key": key, "title": title, "ok": bool(ok), "who": who, "hint": hint, "detail": detail})

    py_ok = sys.version_info >= (3, 9)
    add("python", "Python 3.9+", py_ok, "human", "поставить Python 3.9 или новее", sys.version.split()[0])
    try:
        import telethon  # noqa: F401
        have_telethon = True
    except ImportError:
        have_telethon = False
    add("deps", "Зависимости установлены (venv + telethon)", have_telethon, "agent",
        "запустить setup.sh", "")
    claude = config.find_claude()
    add("claude", "Найден claude CLI (им оценивается находка)", claude, "human",
        "установить Claude Code и войти в него", claude or "")

    niche_ok = config.NICHE_FILE.exists() and PLACEHOLDER not in config.NICHE_FILE.read_text(encoding="utf-8")
    add("niche", "Профиль ниши заполнен (data/niche.md)", niche_ok, "agent",
        "провести интервью про нишу (шаг «Ниша»)", "")
    api_ok = bool(config.get("TG_API_ID") and config.get("TG_API_HASH") and config.get("TG_PHONE"))
    add("tg_creds", "Данные Телеграм-приложения (api_id, api_hash, номер)", api_ok, "human",
        "получить на my.telegram.org и записать (шаг «Телеграм»)", "")

    authorized, groups = False, 0
    if have_telethon and api_ok and not offline:
        res = subprocess.run([sys.executable, str(config.ROOT / "lovec" / "login.py"), "status", "--json"],
                             capture_output=True, text=True)
        try:
            info = json.loads(res.stdout.strip().splitlines()[-1])
            authorized, groups = info.get("authorized", False), info.get("groups", 0)
        except (ValueError, IndexError):
            pass
    add("tg_login", "Вход в Телеграм выполнен", authorized, "human",
        "ввести код из Телеграма (login.sh code)", "офлайн-режим, не проверялось" if offline else "")
    add("chats", "Аккаунт состоит в тематических группах (лучше 10+)", groups >= 1, "human",
        "вступить в чаты своей ниши — ловец ищет только там, где ты состоишь",
        "групп: %d%s" % (groups, "" if groups >= 10 or not groups else ", маловато — улова будет мало"))

    phrases = []
    if config.PHRASES_FILE.exists():
        phrases = [l for l in config.PHRASES_FILE.read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.strip().startswith("#")]
    add("phrases", "Есть хотя бы 5 поисковых фраз", len(phrases) >= 5, "agent",
        "составить и проверить фразы (шаг «Фразы»)", "фраз: %d" % len(phrases))

    add("bot", "Бот для уведомлений (токен)", bool(config.get("TG_BOT_TOKEN")), "human",
        "создать бота в @BotFather и записать токен (шаг «Уведомления»)", "")
    add("chat_id", "Адрес доставки уведомлений известен", bool(config.get("TG_NOTIFY_CHAT")), "agent",
        "найти chat_id: notify.py setup", "")
    conn = db.open_db()
    test_ok = bool(db.meta_get(conn, "notify_test_ok"))
    add("notify_test", "Пробное уведомление дошло", test_ok, "agent", "notify.py test", "")
    last_run = db.meta_get(conn, "last_run")
    add("first_run", "Был хотя бы один боевой прогон", bool(last_run), "agent", "run.py --force",
        last_run or "")
    s = sched.status()
    add("schedule", "Расписание установлено", s["installed"], "agent",
        "schedule.py install", s["detail"])
    office = config.get("LOVEC_OFFICE")
    office_ok = bool(office) and (office == "none" or (
        (Path(office) / ".claude/skills/lovec-daily/SKILL.md").exists()))
    add("office", "Встроен в офис (скиллы и заметка) либо отмечено «офиса нет»", office_ok, "agent",
        "шаг «Офис»: install_skills.py <папка-офиса>", office or "")
    return items


def main():
    offline = "--offline" in sys.argv
    items = check(offline)
    nxt = next((i["key"] for i in items if not i["ok"]), None)
    # если следующий пункт за человеком, а его сейчас нет, — первый красный из тех, что делает агент
    nxt_agent = next((i["key"] for i in items if not i["ok"] and i["who"] == "agent"), None)
    if "--json" in sys.argv:
        print(json.dumps({"next": nxt, "next_agent": nxt_agent, "items": items}, ensure_ascii=False, indent=1))
        return 0
    for i in items:
        print("%s %-52s %s%s" % ("✅" if i["ok"] else "⬜", i["title"],
                                 ("[" + i["detail"] + "] ") if i["detail"] else "",
                                 "" if i["ok"] else "→ " + i["hint"] + " (" + ("тебе" if i["who"] == "human" else "сделаю сам") + ")"))
    print("\nСледующий шаг: %s" % (nxt or "всё готово 🎉"))
    if nxt_agent and nxt_agent != nxt:
        print("Если человека сейчас нет рядом, можно делать без него: %s" % nxt_agent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
