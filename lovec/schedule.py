#!/usr/bin/env python3
"""Расписание ловца: Linux/Mac. Ставит запуск run.py каждые N минут (активные часы run.py
соблюдает сам, по LOVEC_ACTIVE_HOURS).

  schedule.py status
  schedule.py install [--every 60]     каждые N минут (по умолчанию 60)
  schedule.py remove

Linux — строка в crontab с меткой «# lovec-lite». Mac — LaunchAgent в ~/Library/LaunchAgents.
Windows не поддерживается: работай через WSL.
"""
import platform
import subprocess
import sys
from pathlib import Path

import config

MARK = "# lovec-lite"
PLIST = Path.home() / "Library/LaunchAgents/lovec-lite.plist"


def _cmd():
    py = config.ROOT / "venv" / "bin" / "python"
    return "cd %s && %s %s >> %s 2>&1" % (config.ROOT, py, config.ROOT / "lovec" / "run.py", config.LOG_FILE)


def _crontab():
    res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else ""


def status():
    system = platform.system()
    if system == "Darwin":
        return {"installed": PLIST.exists(), "detail": str(PLIST) if PLIST.exists() else ""}
    if system == "Linux":
        line = next((l for l in _crontab().splitlines() if MARK in l), "")
        return {"installed": bool(line), "detail": line.split(" cd ")[0] if line else ""}
    return {"installed": False, "detail": "эта система не поддерживается (нужен Linux, Mac или WSL)"}


def install(every):
    system = platform.system()
    if system == "Linux":
        keep = [l for l in _crontab().splitlines() if MARK not in l]
        step = "*/%d" % every if every < 60 else "7"
        keep.append("%s * * * * %s %s" % (step, _cmd(), MARK))
        res = subprocess.run(["crontab", "-"], input="\n".join(keep) + "\n", text=True)
        if res.returncode:
            print("⛔ не удалось записать crontab")
            return 1
    elif system == "Darwin":
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        PLIST.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>lovec-lite</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>-lc</string><string>%s</string></array>
<key>StartInterval</key><integer>%d</integer>
<key>RunAtLoad</key><false/>
</dict></plist>
""" % (_cmd(), every * 60), encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        subprocess.run(["launchctl", "load", str(PLIST)], check=False)
    else:
        print("⛔ эта система не поддерживается: нужен Linux, Mac или WSL")
        return 1
    print("✅ расписание установлено: каждые %d мин (в активные часы %s)" % (every, config.get("LOVEC_ACTIVE_HOURS")))
    return 0


def remove():
    system = platform.system()
    if system == "Linux":
        keep = [l for l in _crontab().splitlines() if MARK not in l]
        subprocess.run(["crontab", "-"], input="\n".join(keep) + ("\n" if keep else ""), text=True)
    elif system == "Darwin" and PLIST.exists():
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        PLIST.unlink()
    print("✅ расписание снято")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "install":
        every = int(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else 60
        return install(every)
    if cmd == "remove":
        return remove()
    s = status()
    print(("✅ установлено: " if s["installed"] else "⬜ не установлено ") + s["detail"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
