#!/usr/bin/env python3
"""Уведомления в Телеграм: новый горячий запрос → сообщение от твоего бота.

Панели нет: всё, что нужно для решения «писать или нет», лежит в самом сообщении — кто, где,
что написал, почему такой балл и готовый заход. Каждый лид приходит один раз.

  notify.py            отправить новых горячих (внутри run.py)
  notify.py --dry-run  показать, что ушло бы, ничего не отправляя
  notify.py setup      найти твой chat_id: сначала напиши боту /start
  notify.py test       прислать пробное сообщение
"""
import html
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import config
import db


def api(method, payload):
    token = config.get("TG_BOT_TOKEN")
    if not token:
        raise RuntimeError("нет TG_BOT_TOKEN в data/.env")
    data = urllib.parse.urlencode(payload).encode()
    url = "https://api.telegram.org/bot%s/%s" % (token, method)
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:      # Телеграм объясняет причину в теле ответа
        return json.loads(e.read().decode("utf-8") or "{}") or {"ok": False, "description": str(e)}


def send(text, dry_run=False):
    chat = config.get("TG_NOTIFY_CHAT")
    if dry_run:
        print("--- dry-run ---\n" + text + "\n")
        return True
    if not chat:
        print("⛔ нет TG_NOTIFY_CHAT в data/.env (запусти `notify.py setup`)")
        return False
    payload = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    thread = config.get("TG_NOTIFY_THREAD")
    if thread:
        payload["message_thread_id"] = thread
    resp = api("sendMessage", payload)
    if not resp.get("ok"):
        print("⛔ Телеграм не принял сообщение: %s" % resp.get("description"))
    return bool(resp.get("ok"))


def lead_text(r):
    who = ("<a href=\"https://t.me/%s\">@%s</a>" % (r["author_username"], r["author_username"])
           if r["author_username"] else
           "без ника (%s)" % html.escape(r["author_name"] or str(r["author_id"])))
    snippet = html.escape((r["text"] or "").replace("\n", " ").strip()[:350])
    parts = ["🔥 <b>Новый запрос — %d баллов</b>" % r["score"],
             "%s · %s · %s" % (db.to_local(r["posted_at"]), html.escape(r["chat"] or "чат"), who),
             "", snippet + ("…" if len(r["text"] or "") > 350 else "")]
    if r["rationale"]:
        parts += ["", "<b>Почему:</b> " + html.escape(r["rationale"])]
    if r["scenario"]:
        parts += ["", "<b>Заход:</b> " + html.escape(r["scenario"])]
    parts += ["", "<a href=\"%s\">Сам пост</a>" % html.escape(r["url"], quote=True)]
    return "\n".join(parts)


def candidates(conn):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.get_int("LOVEC_MAX_AGE_DAYS", 3))
              ).strftime("%Y-%m-%d %H:%M:%S")
    return conn.execute(
        "SELECT * FROM leads WHERE score >= ? AND notified_at IS NULL AND prefiltered=0 "
        "AND posted_at >= ? ORDER BY score DESC, posted_at DESC",
        (config.get_int("LOVEC_MIN_NOTIFY", 60), cutoff)).fetchall()


def run(dry_run=False):
    conn = db.open_db()
    rows = candidates(conn)
    cap = config.get_int("LOVEC_MAX_NOTIFY_PER_RUN", 5)
    sent = 0
    for r in rows[:cap]:
        if send(lead_text(r), dry_run):
            sent += 1
            if not dry_run:
                conn.execute("UPDATE leads SET notified_at=? WHERE url=?", (db.now_utc(), r["url"]))
                conn.commit()
    left = max(0, len(rows) - cap)
    print("✅ отправлено уведомлений: %d%s" % (sent, (", ещё %d ждут следующего прогона" % left) if left else ""))
    return 0


def setup():
    resp = api("getUpdates", {"timeout": 0})
    if not resp.get("ok"):
        print("⛔ %s" % resp.get("description"))
        return 1
    chats = {}
    for u in resp.get("result", []):
        m = u.get("message") or u.get("my_chat_member") or {}
        c = m.get("chat")
        if c:
            chats[c["id"]] = c.get("title") or c.get("first_name") or str(c["id"])
    if not chats:
        print("⛔ боту пока никто не писал. Открой своего бота в Телеграме, нажми Start (или добавь его "
              "в группу и напиши там), потом запусти это ещё раз.")
        return 1
    for cid, title in chats.items():
        print("chat_id=%s  (%s)" % (cid, title))
    return 0


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "setup":
        return setup()
    if arg == "test":
        ok = send("✅ <b>Ловец запросов подключён.</b>\nКогда найду горячий запрос — пришлю сюда.")
        if ok:
            db.meta_set(db.open_db(), "notify_test_ok", db.now_utc())
            print("✅ пробное сообщение ушло")
        return 0 if ok else 1
    return run(dry_run=(arg == "--dry-run"))


if __name__ == "__main__":
    sys.exit(main())
