"""Пути и настройки ловца. Всё, что принадлежит человеку (ключи, вход в Телеграм, найденное),
лежит в data/ и в git не попадает. Код — только в lovec/."""
import os
import shutil
from pathlib import Path

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
    "LOVEC_MODEL_BULK": "haiku",        # массовый разбор: задача простая
    "LOVEC_MODEL_HOT": "sonnet",        # заход в личку у горячих пишет модель посильнее
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
    os.chmod(ENV_FILE, 0o600)


def find_claude():
    """Путь к claude CLI. Из крона PATH урезан, поэтому смотрим и привычные места."""
    explicit = get("LOVEC_CLAUDE_BIN")
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    for cand in (home / ".local/bin/claude", home / ".claude/local/claude",
                 Path("/usr/local/bin/claude"), Path("/opt/homebrew/bin/claude")):
        if cand.exists():
            return str(cand)
    return None


def active_hours():
    raw = get("LOVEC_ACTIVE_HOURS", "8-22")
    try:
        a, b = raw.split("-")
        return int(a), int(b)
    except ValueError:
        return 8, 22
