#!/usr/bin/env python3
"""Поиск запросов по группам Телеграма, где состоит аккаунт: фразы из data/phrases.txt → база.

Что известно по живым прогонам автора и заложено здесь:
  * Телеграм ищет не фразу, а слова порознь, поэтому каждая фраза идёт в кавычках;
  * кавычки ищут сочетание целиком, значит фразы короткие — 2-4 слова, длинная даёт ноль;
  * склонения Телеграм понимает сам, перечислять их не надо;
  * поиск видит только то, где состоит твой аккаунт, — поэтому важны чаты (см. онбординг);
  * лички, свои сообщения, ботов и каналы-трансляции пропускаем: лид — человек в группе.

  search.py                       обычный прогон по всем фразам
  search.py --probe "фраза" [-d 14]   проверить одну фразу: сколько находит и что именно (в базу не пишет)
"""
import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from telethon import errors, functions, types

import config
import db
import login

PAUSE = 1.2     # между запросами, чтобы не ловить флуд-лимит


def read_phrases():
    if not config.PHRASES_FILE.exists():
        return []
    out = []
    for line in config.PHRASES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip().strip('"«»“”').strip()    # кавычки вокруг фразы ловец ставит сам
        if line and not line.startswith("#"):
            out.append(line)
    return out


async def search_phrase(client, query, limit, min_date):
    got, rate, offset_id, offset_peer = [], 0, 0, types.InputPeerEmpty()
    while len(got) < limit:
        try:
            res = await client(functions.messages.SearchGlobalRequest(
                q=query, filter=types.InputMessagesFilterEmpty(), min_date=min_date, max_date=None,
                offset_rate=rate, offset_peer=offset_peer, offset_id=offset_id, limit=100,
                groups_only=True))
        except errors.FloodWaitError as e:
            if e.seconds > 120:
                print("   флуд-лимит %s сек — фразу пропускаем" % e.seconds)
                break
            print("   флуд-лимит, ждём %s сек" % e.seconds)
            await asyncio.sleep(e.seconds + 1)
            continue
        entities = {x.id: x for x in list(res.chats) + list(res.users)}
        messages = [m for m in res.messages if isinstance(m, types.Message)]
        if not messages:
            break
        got.extend((m, entities) for m in messages)
        last = messages[-1]
        rate = getattr(res, "next_rate", 0) or rate
        offset_id = last.id
        peer = last.peer_id
        cid = (getattr(peer, "channel_id", None) or getattr(peer, "chat_id", None)
               or getattr(peer, "user_id", None))
        try:
            offset_peer = await client.get_input_entity(entities.get(cid))
        except Exception:
            break
        if len(messages) < 100:
            break
        await asyncio.sleep(PAUSE)
    return got[:limit]


def to_lead(message, entities, phrase):
    """Сообщение → запись лида или None, если это не человек в группе / нет ссылки."""
    peer = message.peer_id
    if isinstance(peer, types.PeerUser) or getattr(message, "out", False):
        return None
    sender = entities.get(getattr(message, "sender_id", None))
    if not isinstance(sender, types.User) or sender.bot:
        return None
    text = (message.message or "").strip()
    if not text:
        return None
    channel_id = getattr(peer, "channel_id", None)
    cid = channel_id or getattr(peer, "chat_id", None)
    chat = entities.get(cid)
    uname = getattr(chat, "username", None)
    if uname:
        url = "https://t.me/%s/%d" % (uname, message.id)
    elif channel_id:
        url = "https://t.me/c/%d/%d" % (channel_id, message.id)   # откроется у тех, кто в группе
    else:
        return None
    name = ("%s %s" % (sender.first_name or "", sender.last_name or "")).strip()
    return {
        "url": url, "chat": getattr(chat, "title", None) or str(cid),
        "author_id": sender.id, "author_username": sender.username or "", "author_name": name,
        "text": text, "posted_at": message.date.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "phrase": phrase,
    }


async def probe(phrase, days):
    c = login.client()
    await c.connect()
    if not await c.is_user_authorized():
        print("⛔ входа в Телеграм нет")
        return 1
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await search_phrase(c, '"%s"' % phrase, 100, since)
    leads = [x for x in (to_lead(m, e, phrase) for m, e in rows) if x]
    await c.disconnect()
    print("«%s» за %d дн.: сообщений в выдаче %d, из них людей в группах %d"
          % (phrase, days, len(rows), len(leads)))
    for l in leads[:6]:
        print("  · [%s] %s" % (l["chat"][:30], l["text"].replace("\n", " ")[:170]))
    return 0


async def run():
    phrases = read_phrases()
    if not phrases:
        print("⛔ в data/phrases.txt нет фраз")
        return 1
    conn = db.open_db()
    c = login.client()
    await c.connect()
    if not await c.is_user_authorized():
        print("⛔ связь с Телеграмом слетела: нужно заново войти (login.py request)")
        return 1
    lookback = config.get_int("LOVEC_LOOKBACK_DAYS", 7)
    per_phrase = config.get_int("LOVEC_PER_PHRASE", 100)
    started = db.now_utc()
    added = 0
    for i, phrase in enumerate(phrases, 1):
        row = conn.execute("SELECT last_run FROM phrase_state WHERE phrase=?", (phrase,)).fetchone()
        since = db.parse_utc(row["last_run"]) if row else None
        mark = "с прошлого раза"
        if not since:
            since = datetime.now(timezone.utc) - timedelta(days=lookback)
            mark = "первый раз, %d дн." % lookback
        rows = await search_phrase(c, '"%s"' % phrase, per_phrase, since)
        fresh = 0
        for message, entities in rows:
            lead = to_lead(message, entities, phrase)
            if not lead:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO leads(url,chat,author_id,author_username,author_name,text,"
                "posted_at,phrase,found_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (lead["url"], lead["chat"], lead["author_id"], lead["author_username"],
                 lead["author_name"], lead["text"], lead["posted_at"], lead["phrase"], started))
            fresh += cur.rowcount
        conn.execute("INSERT INTO phrase_state(phrase,last_run) VALUES(?,?) "
                     "ON CONFLICT(phrase) DO UPDATE SET last_run=excluded.last_run", (phrase, started))
        conn.commit()
        added += fresh
        print("[%d/%d] «%s» (%s) — просмотрено %d, новых %d" % (i, len(phrases), phrase, mark, len(rows), fresh))
        await asyncio.sleep(PAUSE)
    await c.disconnect()
    db.meta_set(conn, "last_search", started)
    print("✅ новых записей: %d" % added)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", help="проверить одну фразу, в базу не писать")
    ap.add_argument("-d", "--days", type=int, default=14)
    args = ap.parse_args()
    return asyncio.run(probe(args.probe, args.days) if args.probe else run())


if __name__ == "__main__":
    sys.exit(main())
