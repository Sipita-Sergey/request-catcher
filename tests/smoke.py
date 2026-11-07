#!/usr/bin/env python3
"""Дымовой тест ловца без Телеграма и без настоящей нейросети: Windows, Mac, Linux.

Запуск после установки:  python tests/smoke.py
Проверяет: установку, doctor, оценку через API в формате OpenAI (локальная заглушка) и через
«свою команду», скрытый ввод секрета, прогон с журналом на русском, расписание (ставит и снимает).
Личное не трогает: работает в отдельной папке данных (LOVEC_DATA во временной папке).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIN = os.name == "nt"
PY = ROOT / "venv" / ("Scripts/python.exe" if WIN else "bin/python")
DATA = Path(tempfile.mkdtemp(prefix="lovec-smoke-"))
FAILED = []

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


class Mock(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ids = re.findall(r'"id": "(\d+)"', body["messages"][0]["content"]) or ["0"]
        ans = [{"id": i, "score": 71, "risk": "🟢 Низкий", "rationale": "заглушка API",
                "scenario": "Здравствуйте! Увидел ваш вопрос."} for i in ids]
        out = json.dumps({"choices": [{"message": {"content": json.dumps(ans, ensure_ascii=False)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def run(args, env_extra=None, stdin=None):
    env = dict(os.environ, LOVEC_DATA=str(DATA))
    env.pop("PYTHONUTF8", None)            # проверяем, что ловец сам справляется с кодировкой
    env.pop("PYTHONIOENCODING", None)
    env.update(env_extra or {})
    res = subprocess.run([str(PY), *args], cwd=str(ROOT), env=env, input=stdin, capture_output=True)
    out = (res.stdout + res.stderr).decode("utf-8", errors="replace")
    return res.returncode, out


def check(name, ok, out=""):
    print(("✅ " if ok else "❌ ") + name)
    if not ok:
        FAILED.append(name)
        print("   " + out.strip().replace("\n", "\n   ")[-1500:])


def seed():
    code = (
        "import sys; sys.path.insert(0, 'lovec'); import db\n"
        "c = db.open_db()\n"
        "rows = [('https://t.me/c/1/1', 'Чат предпринимателей', 'Подскажите, кто может настроить чат-бота для записи клиентов? Бюджет есть'),\n"
        "        ('https://t.me/c/1/2', 'Чат предпринимателей', 'Предлагаю свои услуги по созданию ботов, портфолио в личку')]\n"
        "for u, ch, t in rows:\n"
        "    c.execute('INSERT OR REPLACE INTO leads(url,chat,text,posted_at,found_at) VALUES(?,?,?,?,?)', (u, ch, t, db.now_utc(), db.now_utc()))\n"
        "c.execute('UPDATE leads SET scored_at=NULL, score=NULL')\n"
        "c.commit()\n")
    f = DATA / "seed.py"
    f.write_text(code, encoding="utf-8")
    return run([str(f)])


def scores():
    code = ("import sqlite3, sys, json; c = sqlite3.connect(sys.argv[1]);"
            "print(json.dumps([r[0] for r in c.execute('select score from leads order by url')]))")
    f = DATA / "scores.py"
    f.write_text(code, encoding="utf-8")
    rc, out = run([str(f), str(DATA / "lovec.db")])
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return out


def main():
    check("Python окружения есть: %s" % PY, PY.exists())
    rc, out = run(["lovec/doctor.py", "--offline"])
    check("doctor --offline запускается и печатает по-русски", rc == 0 and "Зависимости установлены" in out, out)

    (DATA / "niche.md").write_text("Продаю настройку чат-ботов для записи клиентов.\n", encoding="utf-8")

    srv = HTTPServer(("127.0.0.1", 0), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    api = {"LOVEC_LLM": "api", "LOVEC_API_BASE": "http://127.0.0.1:%d/v1" % srv.server_port,
           "LOVEC_API_MODEL": "test-model", "LOVEC_API_KEY": "x"}
    rc, out = run(["lovec/llm.py", "test"], api)
    check("llm.py test через API в формате OpenAI", rc == 0 and "отвечает" in out, out)
    seed()
    rc, out = run(["lovec/score.py"], api)
    sc = scores()
    check("score.py через API: запрос 71, самореклама отсеяна (10)", sc == [71, 10], "%s\n%s" % (sc, out))

    fake = DATA / "fake_llm.py"
    fake.write_text(
        "import sys, re, json\n"
        "for s in (sys.stdin, sys.stdout):\n"
        "    s.reconfigure(encoding='utf-8')\n"
        "p = sys.stdin.read(); ids = re.findall(r'\"id\": \"(\\d+)\"', p) or ['0']\n"
        "print(json.dumps([{'id': i, 'score': 55, 'rationale': 'своя команда', 'scenario': ''} for i in ids], ensure_ascii=False))\n",
        encoding="utf-8")
    cmd = {"LOVEC_LLM": "cmd", "LOVEC_LLM_CMD": '"%s" "%s"' % (sys.executable, fake)}
    seed()
    rc, out = run(["lovec/score.py"], cmd)
    sc = scores()
    check("score.py через свою команду", sc == [55, 10], "%s\n%s" % (sc, out))

    rc, out = run(["lovec/secret.py", "TG_BOT_TOKEN"], stdin=b"123:abc\n")
    env_text = (DATA / ".env").read_text(encoding="utf-8") if (DATA / ".env").exists() else ""
    check("secret.py записывает секрет в data/.env", rc == 0 and "TG_BOT_TOKEN=123:abc" in env_text, out)

    rc, out = run(["lovec/secret.py", "VK_TOKEN"],
                  stdin=b"https://oauth.vk.com/blank.html#access_token=vk1.a.TEST_123&expires_in=0&user_id=1\n")
    env_text = (DATA / ".env").read_text(encoding="utf-8")
    check("secret.py VK_TOKEN достаёт ключ из адресной строки", rc == 0 and "VK_TOKEN=vk1.a.TEST_123\n" in env_text, out)

    vkt = DATA / "vk_lead.py"
    vkt.write_text(
        "import sys; sys.path.insert(0, 'lovec'); import vk, db, notify\n"
        "item = {'owner_id': -5, 'id': 7, 'date': 1762500000, 'text': 'Девочки, посоветуйте мастера маникюра'}\n"
        "lead = vk.to_lead(item, {}, {5: {'name': 'Подслушано'}}, 'посоветуйте мастера')\n"
        "assert lead['url'] == 'https://vk.com/wall-5_7', lead\n"
        "c = db.open_db()\n"
        "c.execute(\"INSERT OR REPLACE INTO leads(url,chat,author_id,author_username,author_name,text,posted_at,phrase,found_at,source,score,prefiltered) VALUES(?,?,?,?,?,?,datetime('now'),?,datetime('now'),'vk',80,0)\", "
        "(lead['url'], lead['chat'], lead['author_id'], lead['author_username'], lead['author_name'], lead['text'], lead['phrase']))\n"
        "c.commit()\n"
        "r = c.execute('select * from leads where url=?', (lead['url'],)).fetchone()\n"
        "t = notify.lead_text(r)\n"
        "assert 'ВК · Подслушано' in t and 'комментариях' in t and 'vk.com/wall-5_7' in t, t\n"
        "c.execute('delete from leads where url=?', (lead['url'],)); c.commit()\n"
        "print('ok')\n", encoding="utf-8")
    rc, out = run([str(vkt)])
    check("ВК: запись превращается в находку и уведомление", rc == 0 and "ok" in out, out)

    seed()
    rc, out = run(["lovec/run.py", "--force", "--no-search", "--dry-run", "--log"], cmd)
    log = (DATA / "run.log").read_text(encoding="utf-8") if (DATA / "run.log").exists() else ""
    check("run.py --log пишет журнал на русском", rc == 0 and "прогон закончен" in log, out + "\n" + log)

    if os.environ.get("LOVEC_SMOKE_SCHEDULE") == "1":
        rc, out = run(["lovec/schedule.py", "install", "--every", "60"])
        check("schedule.py install", rc == 0 and "установлено" in out, out)
        rc, out = run(["lovec/schedule.py", "status"])
        check("schedule.py status видит задачу", "✅ установлено" in out, out)
        rc, out = run(["lovec/schedule.py", "remove"])
        rc2, out2 = run(["lovec/schedule.py", "status"])
        check("schedule.py remove снимает задачу", "не установлено" in out2, out + out2)

    srv.shutdown()
    print("\nИтог: %s" % ("всё прошло" if not FAILED else "упало %d: %s" % (len(FAILED), "; ".join(FAILED))))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
