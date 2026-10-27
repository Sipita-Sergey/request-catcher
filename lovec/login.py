#!/usr/bin/env python3
"""Вход ловца в Телеграм.

Код из Телеграма и облачный пароль вводит ЧЕЛОВЕК, они не проходят через агента: их читает
login.sh через скрытый ввод и отдаёт сюда по stdin. Ловец только читает (поиск и список
чатов): сообщений от твоего имени не отправляет, в чаты не вступает.

  login.py request     отправить код в Телеграм (нужны TG_API_ID, TG_API_HASH, TG_PHONE)
  login.py code        код со stdin
  login.py password    облачный пароль (если включён) со stdin
  login.py status      [--json] есть ли вход и под кем
  login.py chats       [--json] в каких группах состоит аккаунт: именно там ищет ловец

Коды выхода: 0 — готово · 3 — нужен облачный пароль · 4 — код неверный · 5 — код устарел
· 2 — не хватает настроек.
"""
import asyncio
import json
import os
import sys

from telethon import TelegramClient, errors

import config

STATE = config.DATA / ".login_state.json"


def client():
    try:
        api_id, api_hash = int(config.get("TG_API_ID")), config.get("TG_API_HASH")
    except (TypeError, ValueError):
        api_id, api_hash = None, None
    if not api_id or not api_hash:
        print("⛔ в data/.env нет TG_API_ID / TG_API_HASH")
        sys.exit(2)
    config.DATA.mkdir(parents=True, exist_ok=True)
    return TelegramClient(str(config.SESSION), api_id, api_hash)


def lock_session_file():
    p = str(config.SESSION) + ".session"
    if os.path.exists(p):
        os.chmod(p, 0o600)


async def request():
    phone = config.get("TG_PHONE")
    if not phone:
        print("⛔ в data/.env нет TG_PHONE (номер в формате +79991234567)")
        return 2
    c = client()
    await c.connect()
    if await c.is_user_authorized():
        print("✅ уже вошли, код не нужен")
        await c.disconnect()
        return 0
    sent = await c.send_code_request(phone)
    STATE.write_text(json.dumps({"phone": phone, "hash": sent.phone_code_hash}), encoding="utf-8")
    os.chmod(STATE, 0o600)
    await c.disconnect()
    print("✅ код отправлен в Телеграм на номер %s (придёт в приложение, не смс)" % phone)
    return 0


async def code():
    value = sys.stdin.read().strip().replace(" ", "")
    if not value or not STATE.exists():
        print("⛔ нет кода или не запрошен: сначала `login.py request`")
        return 2
    st = json.loads(STATE.read_text(encoding="utf-8"))
    c = client()
    await c.connect()
    try:
        await c.sign_in(phone=st["phone"], code=value, phone_code_hash=st["hash"])
    except errors.SessionPasswordNeededError:
        await c.disconnect()
        print("🔐 включён облачный пароль — нужен ещё он (`login.sh password`)")
        return 3
    except errors.PhoneCodeInvalidError:
        await c.disconnect()
        print("⛔ код неверный — попробуй ещё раз")
        return 4
    except errors.PhoneCodeExpiredError:
        await c.disconnect()
        print("⛔ код устарел — запроси новый: `login.py request`")
        return 5
    me = await c.get_me()
    await c.disconnect()
    STATE.unlink(missing_ok=True)
    lock_session_file()
    print("✅ вошли как %s" % (("@" + me.username) if me.username else me.first_name))
    return 0


async def password():
    value = sys.stdin.read().rstrip("\n")
    if not value:
        print("⛔ пароль пустой")
        return 2
    c = client()
    await c.connect()
    try:
        await c.sign_in(password=value)
    except errors.PasswordHashInvalidError:
        await c.disconnect()
        print("⛔ пароль неверный")
        return 4
    me = await c.get_me()
    await c.disconnect()
    STATE.unlink(missing_ok=True)
    lock_session_file()
    print("✅ вошли как %s" % (("@" + me.username) if me.username else me.first_name))
    return 0


async def groups(c):
    """Группы (не каналы-трансляции и не личка): только в них люди задают вопросы."""
    out = []
    async for d in c.iter_dialogs():
        ent = d.entity
        is_group = getattr(ent, "megagroup", False) or (d.is_group and not getattr(ent, "broadcast", False))
        if is_group:
            out.append({"title": d.name, "username": getattr(ent, "username", None) or "",
                        "members": getattr(ent, "participants_count", None)})
    return out


async def status(as_json):
    c = client()
    await c.connect()
    res = {"authorized": False}
    if await c.is_user_authorized():
        me = await c.get_me()
        res = {"authorized": True, "me": ("@" + me.username) if me.username else me.first_name,
               "groups": len(await groups(c))}
    await c.disconnect()
    print(json.dumps(res, ensure_ascii=False) if as_json else
          ("✅ вход есть: %(me)s, групп: %(groups)d" % res if res["authorized"] else "⛔ входа нет"))
    return 0 if res["authorized"] else 1


async def chats(as_json):
    c = client()
    await c.connect()
    if not await c.is_user_authorized():
        print("⛔ входа нет")
        return 1
    items = await groups(c)
    await c.disconnect()
    if as_json:
        print(json.dumps(items, ensure_ascii=False))
    else:
        print("групп в аккаунте: %d" % len(items))
        for g in sorted(items, key=lambda x: -(x["members"] or 0))[:60]:
            print("  %s%s · %s уч." % (g["title"], (" @" + g["username"]) if g["username"] else "",
                                       g["members"] if g["members"] is not None else "?"))
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    as_json = "--json" in sys.argv
    handlers = {"request": request, "code": code, "password": password,
                "status": lambda: status(as_json), "chats": lambda: chats(as_json)}
    if cmd not in handlers:
        print(__doc__)
        return 2
    return asyncio.run(handlers[cmd]())


if __name__ == "__main__":
    sys.exit(main())
