#!/usr/bin/env python3
"""Один прогон ловца: поиск → оценка → уведомления. Это то, что запускает расписание.

  run.py              обычный прогон (вне активных часов молчит)
  run.py --force      игнорировать активные часы
  run.py --no-search  только оценить и уведомить то, что уже в базе
  run.py --dry-run    уведомления не отправлять, а показать

Страховки: замок (прогоны не накладываются), раз в сутки короткая сводка (чтобы тишина не
выглядела как «сломалось»), раз в сутки тревога, если поиск или оценка не работают.
"""
import argparse
import fcntl
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import config
import db
import notify

HERE = config.ROOT / "lovec"


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)


def step(script, *args):
    res = subprocess.run([sys.executable, str(HERE / script), *args], capture_output=True, text=True)
    out = (res.stdout + res.stderr).strip()
    if out:
        print(out, flush=True)
    return res.returncode


def alert_once_a_day(conn, key, text, dry_run):
    today = datetime.now().strftime("%Y-%m-%d")
    if db.meta_get(conn, key) == today:
        return
    if not dry_run and notify.send(text):
        db.meta_set(conn, key, today)


def daily_digest(conn, dry_run):
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if now.hour < 21 or db.meta_get(conn, "digest_day") == today:
        return
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    found = conn.execute("SELECT COUNT(*) FROM leads WHERE found_at >= ?", (since,)).fetchone()[0]
    hot = conn.execute("SELECT COUNT(*) FROM leads WHERE found_at >= ? AND score >= ? AND prefiltered=0",
                       (since, config.get_int("LOVEC_MIN_NOTIFY", 60))).fetchone()[0]
    sent = conn.execute("SELECT COUNT(*) FROM leads WHERE notified_at >= ?", (since,)).fetchone()[0]
    text = ("🌙 <b>Ловец за сутки</b>\nнайдено сообщений: %d · горячих: %d · прислал тебе: %d\n"
            "Работаю, если тихо — значит подходящих запросов не было." % (found, hot, sent))
    if not dry_run and notify.send(text):
        db.meta_set(conn, "digest_day", today)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-search", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    config.DATA.mkdir(parents=True, exist_ok=True)
    lock = open(config.DATA / "run.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("прогон пропущен — предыдущий ещё идёт")
        return 0

    start, end = config.active_hours()
    if not args.force and not (start <= datetime.now().hour < end):
        return 0

    conn = db.open_db()
    log("=== прогон начат ===")
    search_rc = 0
    if not args.no_search:
        log("1/3 поиск в Телеграме")
        search_rc = step("search.py")
        if search_rc:
            alert_once_a_day(conn, "alert_search_day",
                             "⚠️ <b>Ловец не может искать в Телеграме.</b>\nЧаще всего слетел вход — открой своего "
                             "помощника и скажи «настрой ловца» (он увидит, что не так).", args.dry_run)
    log("2/3 оценка")
    score_rc = step("score.py")
    if score_rc:
        alert_once_a_day(conn, "alert_score_day",
                         "⚠️ <b>Ловец не может оценивать находки.</b>\nЧаще всего упёрлись в лимит подписки Claude "
                         "или не найден claude CLI. Найденное не потеряется — оценю в следующий прогон.", args.dry_run)
    log("3/3 уведомления")
    notify.run(dry_run=args.dry_run)
    daily_digest(conn, args.dry_run)
    db.meta_set(conn, "last_run", db.now_utc())
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    log("=== прогон закончен, записей в базе: %d ===" % total)

    if config.LOG_FILE.exists() and config.LOG_FILE.stat().st_size > 1_000_000:
        tail = config.LOG_FILE.read_text(encoding="utf-8", errors="ignore")[-300_000:]
        config.LOG_FILE.write_text(tail, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
