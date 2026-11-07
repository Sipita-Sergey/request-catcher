"""Пути и настройки ловца. Всё, что принадлежит человеку (ключи, вход в Телеграм, найденное),
лежит в data/ и в git не попадает. Код — только в lovec/."""
import os
import platform
import shutil
import sys
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"

# Windows по умолчанию пишет в консоль в cp1251/cp866: русский текст и эмодзи там падают с
# UnicodeEncodeError. Переводим вывод на UTF-8, а дочерним процессам ставим тот же режим.
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("LOVEC_DATA") or ROOT / "data")
ENV_FILE = DATA / ".env"
SESSION = DATA / "session"
DB_FILE = DATA / "lovec.db"
PHRASES_FILE = DATA / "phrases.txt"
NICHE_FILE = DATA / "niche.md"
STATE_FILE = DATA / "setup-state.md"
LOG_FILE = DATA / "run.log"

DEFAULTS = {
    # LOVEC_LLM — чем оценивать: claude | codex | gemini | qwen | api | cmd. Пусто — сам находит,
    # что установлено (порядок в llm.py). LOVEC_MODEL_BULK / LOVEC_MODEL_HOT — модели этой нейросети
    # для массового разбора и для горячих; пусто — умолчание выбранной нейросети (llm.py).
    "LOVEC_LOOKBACK_DAYS": "7",         # новая фраза: сколько дней истории взять в первый раз
    "LOVEC_PER_PHRASE": "100",          # максимум сообщений на фразу за прогон
    "LOVEC_MAX_SCORE_PER_RUN": "150",   # потолок обращений к модели за прогон
    "LOVEC_MIN_NOTIFY": "60",           # с какого балла дёргаем уведомлением
    "LOVEC_MAX_AGE_DAYS": "3",          # пост старше — не лид, писать поздно
    "LOVEC_MAX_NOTIFY_PER_RUN": "5",    # чтобы разовый улов не стал спамом
    "LOVEC_ACTIVE_HOURS": "8-22",       # вне этих часов (по времени машины) прогон молчит
}


def read_env_file(path=None):
    path = Path(path or ENV_FILE)
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get(key, default=None):
    """Порядок: переменная окружения → data/.env → умолчание из DEFAULTS → default."""
    if os.environ.get(key):
        return os.environ[key]
    val = read_env_file().get(key)
    if val:
        return val
    return DEFAULTS.get(key, default)


def get_int(key, default=0):
    try:
        return int(get(key, default))
    except (TypeError, ValueError):
        return int(default)


def set_value(key, value):
    """Дописывает/заменяет KEY=value в data/.env (права 600). Для несекретных значений."""
    DATA.mkdir(parents=True, exist_ok=True)
    lines = []
    if ENV_FILE.exists():
        lines = [l for l in ENV_FILE.read_text(encoding="utf-8").splitlines()
                 if not l.startswith(key + "=")]
    lines.append("%s=%s" % (key, value))
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lock_file(ENV_FILE)


def lock_file(path):
    """Права «только владелец». На Windows chmod почти ничего не значит — там файл и так в
    профиле пользователя, ошибку не считаем поломкой."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def venv_python():
    """Python окружения ловца: на Mac/Linux venv/bin/python, на Windows venv\\Scripts\\python.exe."""
    win = ROOT / "venv" / "Scripts" / "python.exe"
    nix = ROOT / "venv" / "bin" / "python"
    if win.exists():
        return win
    if nix.exists():
        return nix
    return Path(sys.executable)


def find_bin(name, env_key=None):
    """Путь к программе (claude, codex, gemini, qwen). Из расписания PATH урезан, поэтому
    смотрим и привычные места установки на Mac, Linux и Windows."""
    if env_key:
        explicit = get(env_key)
        if explicit and Path(explicit).exists():
            return explicit
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    cands = [home / ".local/bin" / name, home / (".%s/local" % name) / name,
             Path("/usr/local/bin") / name, Path("/opt/homebrew/bin") / name,
             home / ".npm-global/bin" / name]
    if IS_WINDOWS:
        appdata = Path(os.environ.get("APPDATA") or home / "AppData/Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local")
        for base in (appdata / "npm", home / ".local/bin", local / "Programs" / name,
                     home / (".%s/local" % name)):
            for ext in (".exe", ".cmd", ".bat", ""):
                cands.append(base / (name + ext))
    for cand in cands:
        if cand.exists():
            return str(cand)
    return None


def find_claude():
    return find_bin("claude", "LOVEC_CLAUDE_BIN")


def active_hours():
    raw = get("LOVEC_ACTIVE_HOURS", "8-22")
    try:
        a, b = raw.split("-")
        return int(a), int(b)
    except ValueError:
        return 8, 22
