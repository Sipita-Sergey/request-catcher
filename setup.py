#!/usr/bin/env python3
"""Установка ловца: окружение + пустые заготовки в data/. Безопасно запускать повторно.
Одна и та же команда для Windows, Mac и Linux:

  Windows:     py setup.py        (или python setup.py)
  Mac/Linux:   python3 setup.py
"""
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIN = os.name == "nt"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def venv_python():
    return HERE / "venv" / ("Scripts/python.exe" if WIN else "bin/python")


def main():
    if sys.version_info < (3, 9):
        print("⛔ Python старше 3.9 (%s). Нужен 3.9 или новее." % sys.version.split()[0])
        return 1
    py = venv_python()
    if not py.exists():
        try:
            venv.EnvBuilder(with_pip=True).create(str(HERE / "venv"))
        except Exception as e:  # noqa: BLE001 — человеку нужна причина словами, а не трасса
            print("⛔ не создалось окружение: %s" % e)
            if not WIN:
                print("   На Debian/Ubuntu: sudo apt install python3-venv")
            return 1
    env = dict(os.environ, PYTHONUTF8="1")
    rc = subprocess.run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"], env=env).returncode
    rc = rc or subprocess.run([str(py), "-m", "pip", "install", "-q", "-r", str(HERE / "requirements.txt")],
                              env=env).returncode
    if rc:
        print("⛔ не установились зависимости (нет интернета или pypi.org закрыт)")
        return 1
    print("✅ окружение и зависимости готовы")

    data = HERE / "data"
    data.mkdir(exist_ok=True)
    for src, dst in (("templates/niche.md", "niche.md"), ("templates/phrases.example.txt", "phrases.txt"),
                     ("templates/vk_phrases.example.txt", "vk_phrases.txt")):
        if not (data / dst).exists():
            shutil.copyfile(HERE / src, data / dst)
    envf = data / ".env"
    if not envf.exists():
        envf.touch()
    try:
        os.chmod(envf, 0o600)
    except OSError:
        pass
    print("✅ заготовки в data/ созданы (ниша, фразы, настройки) — это твои файлы, в git они не попадают")
    print("Python ловца: %s" % py)
    return 0


if __name__ == "__main__":
    sys.exit(main())
