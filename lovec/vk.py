#!/usr/bin/env python3
"""Поиск запросов во ВКонтакте: фразы из data/vk_phrases.txt → та же база, та же оценка и те же
уведомления, что у Телеграма.

ВК ищет по ОТКРЫТЫМ записям всего ВКонтакте (метод newsfeed.search): стены людей и сообществ,
включая «предложку» городских пабликов. Вступать никуда не нужно — в отличие от Телеграма. Беседы
(чаты) ВК открытым поиском не видны.

Что известно по живым замерам автора (21.08.2026, 36 фраз, 1775 записей) и заложено здесь:
  * кавычки ВК игнорирует и ищет по смыслу, поэтому фразы КОРОТКИЕ, 2-3 слова: «ищу разработчика»,
    «нужен специалист»; фраза из 4-7 слов даёт ноль точных попаданий;
  * склонения ВК понимает сам;
  * без окна по времени ВК отдаёт только ~1,5 часа истории — поэтому ищем окном «с прошлого прогона»;
  * не больше 200 записей на страницу, дальше листаем через next_from; 3 запроса в секунду.

Ключ: VK_TOKEN в data/.env (вводится скрыто: `secret.py VK_TOKEN`, можно вставить всю адресную
строку после входа — ключ из неё достанется сам). Годится пользовательский ключ или сервисный ключ
приложения.

  vk.py                           обычный прогон по всем фразам
  vk.py --probe "фраза" [-d 3]    проверить одну фразу: сколько находит и что именно (в базу не пишет)
  vk.py check                     работает ли ключ
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import config
import db

API_VERSION = "5.199"
PAUSE = 0.4                 # ВК: не больше 3 запросов в секунду
PAGE = 200                  # больше ВК не отдаёт
LONG_POST = 2500            # длинный пост почти всегда контент сообщества, а не чей-то запрос

VK_PHRASES_FILE = config.DATA / "vk_phrases.txt"


class VKError(Exception):
    def __init__(self, code, msg):
        super().__init__("ВК %s: %s" % (code, msg))
        self.code = code


def token():
    return (config.get("VK_TOKEN") or "").strip()


def call(method, **params):
    params.update({"access_token": token(), "v": API_VERSION})
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request("https://api.vk.com/method/" + method, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read().decode("utf-8"))
    if "error" in res:
        err = res["error"]
        raise VKError(err.get("error_code"), err.get("error_msg"))
    return res["response"]


def explain(e):
    """Ошибка ВК → что это значит человеку."""
    if isinstance(e, VKError):
        if e.code == 5:
            return "ключ ВК недействителен или устарел — получи новый (шаг «ВКонтакте»)"
        if e.code == 27:
            return "это ключ сообщества, а искать по ВК с ним нельзя — нужен ключ пользователя (шаг «ВКонтакте»)"
        if e.code in (6, 9, 29):
            return "ВК просит притормозить (лимит запросов) — продолжу в следующий прогон"
        if e.code == 15:
            return "ВК не дал доступ этим ключом — получи ключ заново по ссылке из шага «ВКонтакте»"
    return str(e)


def read_phrases():
    if not VK_PHRASES_FILE.exists():
        return []
    out = []
    for line in VK_PHRASES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip().strip('"«»“”').strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def search(phrase, since, limit):
    """Записи по фразе с момента since (UTC), до limit штук, с листанием."""
    got, profiles, groups, start_from = [], {}, {}, None
    start_ts = int(since.timestamp())
    end_ts = int(datetime.now(timezone.utc).timestamp())
    while len(got) < limit:
        params = {"q": phrase, "count": min(PAGE, limit - len(got)), "extended": 1,
                  "start_time": start_ts, "end_time": end_ts}
        if start_from:
            params["start_from"] = start_from
        res = call("newsfeed.search", **params)
        items = res.get("items", [])
        for p in res.get("profiles", []):
            profiles[p["id"]] = p
        for g in res.get("groups", []):
            groups[g["id"]] = g
        got.extend(items)
        start_from = res.get("next_from")
        if not items or not start_from:
            break
        time.sleep(PAUSE)
    return got[:limit], profiles, groups


def to_lead(item, profiles, groups, phrase):
    """Запись ВК → лид или None (пусто, репост без текста, слишком длинный контент)."""
    text = (item.get("text") or "").strip()
    if not text or len(text) > LONG_POST:
        return None
    owner, post_id = item.get("owner_id"), item.get("id")
    if owner is None or post_id is None:
        return None
    signer = item.get("signer_id")          # автор записи в «предложке» сообщества
    author = signer or (owner if owner > 0 else item.get("from_id"))
    if owner > 0:
        chat = "ВК · стена человека"
    else:
        g = groups.get(abs(owner), {})
        chat = "ВК · %s" % (g.get("name") or "сообщество")
    name, uname = "", ""
    if author and author > 0:
        p = profiles.get(author, {})
        name = ("%s %s" % (p.get("first_name", ""), p.get("last_name", ""))).strip()
        uname = p.get("screen_name") or "id%d" % author
    # автор < 0 — запись от имени сообщества (чаще всего анонимная «предложка»): человека не видно,
    # отвечать можно только комментарием под постом — так и пишем в уведомлении
    posted = datetime.fromtimestamp(item.get("date", 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return {"url": "https://vk.com/wall%s_%s" % (owner, post_id), "chat": chat,
            "author_id": author or 0, "author_username": uname, "author_name": name,
            "text": text, "posted_at": posted, "phrase": phrase}


def check():
    if not token():
        print("⛔ нет VK_TOKEN в data/.env (шаг «ВКонтакте»)")
        return 1
    try:
        res = call("newsfeed.search", q="ищу", count=1)
    except (VKError, urllib.error.URLError, OSError) as e:
        print("⛔ " + explain(e))
        return 1
    print("✅ ключ ВК работает, поиск отвечает (записей в пробной выдаче: %d)" % len(res.get("items", [])))
    return 0


def probe(phrase, days):
    if not token():
        print("⛔ нет VK_TOKEN в data/.env")
        return 1
    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        items, profiles, groups = search(phrase, since, 200)
    except (VKError, urllib.error.URLError, OSError) as e:
        print("⛔ " + explain(e))
        return 1
    leads = [x for x in (to_lead(i, profiles, groups, phrase) for i in items) if x]
    exact = [l for l in leads if phrase.lower() in l["text"].lower()]
    print("«%s» за %d дн.: записей %d, подходят по виду %d, фраза дословно в тексте у %d"
          % (phrase, days, len(items), len(leads), len(exact)))
    for l in (exact or leads)[:6]:
        print("  · [%s] %s" % (l["chat"][:30], l["text"].replace("\n", " ")[:170]))
    return 0


def run():
    phrases = read_phrases()
    if not token() or not phrases:
        print("ВК пропущен: %s" % ("нет VK_TOKEN" if not token() else "нет фраз в data/vk_phrases.txt"))
        return 0
    conn = db.open_db()
    lookback = config.get_int("LOVEC_VK_LOOKBACK_HOURS", 24)
    per_phrase = config.get_int("LOVEC_VK_PER_PHRASE", 200)
    started = db.now_utc()
    added, errors_n = 0, 0
    for i, phrase in enumerate(phrases, 1):
        key = "vk:" + phrase
        row = conn.execute("SELECT last_run FROM phrase_state WHERE phrase=?", (key,)).fetchone()
        since = db.parse_utc(row["last_run"]) if row else None
        mark = "с прошлого раза"
        if not since:
            since = datetime.now(timezone.utc) - timedelta(hours=lookback)
            mark = "первый раз, %d ч." % lookback
        try:
            items, profiles, groups = search(phrase, since, per_phrase)
        except (VKError, urllib.error.URLError, OSError) as e:
            errors_n += 1
            print("[%d/%d] «%s» — %s" % (i, len(phrases), phrase, explain(e)))
            if isinstance(e, VKError) and e.code in (5, 15, 27):
                return 1                     # ключ не годится — дальше бессмысленно
            time.sleep(1)
            continue
        fresh = 0
        for item in items:
            lead = to_lead(item, profiles, groups, phrase)
            if not lead:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO leads(url,chat,author_id,author_username,author_name,text,"
                "posted_at,phrase,found_at,source) VALUES(?,?,?,?,?,?,?,?,?,'vk')",
                (lead["url"], lead["chat"], lead["author_id"], lead["author_username"],
                 lead["author_name"], lead["text"], lead["posted_at"], lead["phrase"], started))
            fresh += cur.rowcount
        conn.execute("INSERT INTO phrase_state(phrase,last_run) VALUES(?,?) "
                     "ON CONFLICT(phrase) DO UPDATE SET last_run=excluded.last_run", (key, started))
        conn.commit()
        added += fresh
        print("[%d/%d] «%s» (%s) — просмотрено %d, новых %d" % (i, len(phrases), phrase, mark, len(items), fresh))
        time.sleep(PAUSE)
    db.meta_set(conn, "last_vk_search", started)
    print("✅ ВК: новых записей %d" % added)
    return 1 if errors_n == len(phrases) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="run")
    ap.add_argument("--probe", help="проверить одну фразу, в базу не писать")
    ap.add_argument("-d", "--days", type=int, default=3)
    args = ap.parse_args()
    if args.probe:
        return probe(args.probe, args.days)
    if args.cmd == "check":
        return check()
    return run()


if __name__ == "__main__":
    sys.exit(main())
