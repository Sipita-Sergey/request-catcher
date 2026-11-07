#!/usr/bin/env python3
"""Расписание ловца: Windows, Mac, Linux. Ставит запуск run.py каждые N минут (активные часы
run.py соблюдает сам, по LOVEC_ACTIVE_HOURS).

  schedule.py status
  schedule.py install [--every 60]     каждые N минут (по умолчанию 60)
  schedule.py remove

Linux — строка в crontab с меткой «# lovec-lite». Mac — LaunchAgent в ~/Library/LaunchAgents.
Windows — задача «lovec-lite» в Планировщике заданий (запускается, пока ты вошёл в систему,
без окна консоли). Вывод прогона пишет сам run.py в data/run.log (флаг --log).
"""
import platform
import shlex
import subprocess
import sys
from pathlib import Path

import config

MARK = "# lovec-lite"
TASK = "lovec-lite"
PLIST = Path.home() / "Library/LaunchAgents/lovec-lite.plist"
SYSTEM = platform.system()


def _py():
    return config.venv_python()


def _run_py():
    return config.ROOT / "lovec" / "run.py"


def _crontab():
    try:
        res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    except OSError:
        return ""
    return res.stdout if res.returncode == 0 else ""


def _win_python():
    """pythonw.exe рядом с python.exe: тот же Python, но без мелькающего окна консоли."""
    py = _py()
    w = py.with_name("pythonw.exe")
    return w if w.exists() else py


def _schtasks(*args):
    return subprocess.run(["schtasks", *args], capture_output=True, text=True,
                          encoding="oem" if SYSTEM == "Windows" else "utf-8", errors="replace")


def status():
    if SYSTEM == "Darwin":
        return {"installed": PLIST.exists(), "detail": str(PLIST) if PLIST.exists() else ""}
    if SYSTEM == "Linux":
        line = next((l for l in _crontab().splitlines() if MARK in l), "")
        return {"installed": bool(line), "detail": line.split(" cd ")[0] if line else ""}
    if SYSTEM == "Windows":
        res = _schtasks("/Query", "/TN", TASK)
        return {"installed": res.returncode == 0, "detail": "Планировщик заданий: %s" % TASK if res.returncode == 0 else ""}
    return {"installed": False, "detail": "неизвестная система: %s" % SYSTEM}


def install(every):
    if SYSTEM == "Linux":
        keep = [l for l in _crontab().splitlines() if MARK not in l]
        step = "*/%d" % every if every < 60 else "7"
        cmd = "cd %s && %s %s --log" % (shlex.quote(str(config.ROOT)), shlex.quote(str(_py())),
                                        shlex.quote(str(_run_py())))
        keep.append("%s * * * * %s %s" % (step, cmd, MARK))
        res = subprocess.run(["crontab", "-"], input="\n".join(keep) + "\n", text=True)
        if res.returncode:
            print("⛔ не удалось записать crontab")
            return 1
    elif SYSTEM == "Darwin":
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        PLIST.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>lovec-lite</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>-lc</string><string>%s</string></array>
<key>StartInterval</key><integer>%d</integer>
<key>RunAtLoad</key><false/>
</dict></plist>
""" % ("cd %s && %s %s --log" % (shlex.quote(str(config.ROOT)), shlex.quote(str(_py())),
                                   shlex.quote(str(_run_py()))), every * 60), encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        subprocess.run(["launchctl", "load", str(PLIST)], check=False)
    elif SYSTEM == "Windows":
        tr = '"%s" "%s" --log' % (_win_python(), _run_py())
        res = _schtasks("/Create", "/F", "/TN", TASK, "/SC", "MINUTE", "/MO", str(every), "/TR", tr)
        if res.returncode:
            print("⛔ Планировщик заданий не принял задачу: %s" % (res.stdout + res.stderr).strip()[:300])
            return 1
    else:
        print("⛔ неизвестная система: %s" % SYSTEM)
        return 1
    print("✅ расписание установлено: каждые %d мин (в активные часы %s)" % (every, config.get("LOVEC_ACTIVE_HOURS")))
    return 0


def remove():
    if SYSTEM == "Linux":
        keep = [l for l in _crontab().splitlines() if MARK not in l]
        subprocess.run(["crontab", "-"], input="\n".join(keep) + ("\n" if keep else ""), text=True)
    elif SYSTEM == "Darwin" and PLIST.exists():
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        PLIST.unlink()
    elif SYSTEM == "Windows":
        _schtasks("/Delete", "/F", "/TN", TASK)
    print("✅ расписание снято")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "install":
        every = int(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else 60
        if SYSTEM == "Windows" and every > 1439:
            every = 1439
        return install(every)
    if cmd == "remove":
        return remove()
    s = status()
    print(("✅ установлено: " if s["installed"] else "⬜ не установлено ") + s["detail"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
