#!/usr/bin/env python3
"""Посмотреть, что нашёл ловец. Для ежедневной работы и настройки фраз.

  leads.py top [--days 3] [--min 40] [--limit 15]   лучшие находки
  leads.py show <часть-ссылки>                      одна находка целиком: текст, балл, заход
  leads.py phrases [--days 14]                      какие фразы приносят людей, а какие мусор
  leads.py stats                                    общая картина
  leads.py rescore [--days 3]                       переоценить недавние (после правки профиля ниши)
"""
import argparse
from datetime import datetime, timedelta, timezone

import db


def since(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def top(conn, a):
    rows = conn.execute("SELECT * FROM leads WHERE score >= ? AND posted_at >= ? AND prefiltered=0 "
                        "ORDER BY score DESC, posted_at DESC LIMIT ?", (a.min, since(a.days), a.limit)).fetchall()
    if not rows:
        print("за %d дн. нет находок от %d баллов" % (a.days, a.min))
    for r in rows:
        who = ("@" + r["author_username"]) if r["author_username"] else (r["author_name"] or "без ника")
        print("%3d %s · %s · %s\n    %s\n    %s\n" % (r["score"], db.to_local(r["posted_at"]), (r["chat"] or "")[:28], who,
                                                      (r["text"] or "").replace("\n", " ")[:200], r["url"]))


def show(conn, a):
    r = conn.execute("SELECT * FROM leads WHERE url LIKE ? LIMIT 1", ("%" + a.part + "%",)).fetchone()
    if not r:
        print("не нашёл")
        return
    for k in ("url", "chat", "author_username", "author_name", "posted_at", "phrase", "score", "band",
              "risk", "rationale", "scenario", "notified_at"):
        print("%-16s %s" % (k, r[k]))
    print("\n" + (r["text"] or ""))


def phrases(conn, a):
    rows = conn.execute(
        "SELECT phrase, COUNT(*) n, SUM(CASE WHEN prefiltered=0 AND scored_at IS NOT NULL THEN 1 ELSE 0 END) real, "
        "SUM(CASE WHEN score >= 60 THEN 1 ELSE 0 END) hot FROM leads WHERE found_at >= ? GROUP BY phrase "
        "ORDER BY hot DESC, real DESC", (since(a.days),)).fetchall()
    print("%-34s %8s %8s %8s" % ("фраза", "найдено", "по делу", "горячих"))
    for r in rows:
        print("%-34s %8d %8d %8d" % (r["phrase"][:34], r["n"], r["real"], r["hot"]))
    print("\n«по делу» — прошли предфильтр и оценены моделью. Много найдено, но 0 по делу — фраза ловит болтовню.")


def stats(conn, a):
    q = lambda sql, *p: conn.execute(sql, p).fetchone()[0]
    print("всего в базе: %d" % q("SELECT COUNT(*) FROM leads"))
    print("не оценено: %d" % q("SELECT COUNT(*) FROM leads WHERE scored_at IS NULL"))
    print("горячих (60+): %d" % q("SELECT COUNT(*) FROM leads WHERE score >= 60 AND prefiltered=0"))
    print("отправлено уведомлений: %d" % q("SELECT COUNT(*) FROM leads WHERE notified_at IS NOT NULL"))
    print("последний прогон: %s" % (db.meta_get(conn, "last_run") or "ещё не было"))


def rescore(conn, a):
    cur = conn.execute("UPDATE leads SET scored_at=NULL, score=NULL WHERE posted_at >= ? AND notified_at IS NULL",
                       (since(a.days),))
    conn.commit()
    print("помечено на переоценку: %d (ещё не отправленные в Телеграм); оценятся при следующем прогоне "
          "или командой score.py" % cur.rowcount)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("top"); t.add_argument("--days", type=int, default=3)
    t.add_argument("--min", type=int, default=40); t.add_argument("--limit", type=int, default=15)
    s = sub.add_parser("show"); s.add_argument("part")
    p = sub.add_parser("phrases"); p.add_argument("--days", type=int, default=14)
    sub.add_parser("stats")
    rs = sub.add_parser("rescore"); rs.add_argument("--days", type=int, default=3)
    a = ap.parse_args()
    conn = db.open_db()
    {"top": top, "show": show, "phrases": phrases, "stats": stats, "rescore": rescore}[a.cmd](conn, a)


if __name__ == "__main__":
    main()
