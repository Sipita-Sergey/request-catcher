#!/usr/bin/env python3
"""Чем ловец оценивает находки: любая нейросеть, которая есть у человека.

Ловцу от нейросети нужно одно: получить текст задания и вернуть текст ответа (JSON с баллами).
Это умеет любая модель, поэтому способов подключения несколько, и выбирается тот, что есть:

  claude  Claude Code (подписка Claude)            claude -p, задание через stdin
  codex   Codex CLI (подписка ChatGPT или ключ)     codex exec -, ответ из --output-last-message
  gemini  Gemini CLI (аккаунт Google или ключ)      gemini -p, задание через stdin
  qwen    Qwen Code                                 qwen -p, задание через stdin
  api     любой сервис с API в формате OpenAI       POST {LOVEC_API_BASE}/chat/completions
          (OpenAI, DeepSeek, OpenRouter, Polza, локальная Ollama и др.)
  cmd     любая своя команда                        LOVEC_LLM_CMD: задание в stdin, ответ в stdout

LOVEC_LLM задаёт способ явно. Пусто — берётся первый найденный в порядке AUTO_ORDER.

  llm.py status     что выбрано и почему (для doctor и для человека)
  llm.py test       один короткий запрос: отвечает ли нейросеть
"""
import json
import os
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import config

BACKENDS = ("claude", "codex", "gemini", "qwen", "api", "cmd")
AUTO_ORDER = ("claude", "codex", "gemini", "qwen", "api", "cmd")

# Модели по умолчанию: (массовый разбор, горячие). Пусто — умолчание самой программы:
# у Codex и Gemini оно зависит от тарифа человека, угадывать название модели не надо.
DEFAULT_MODELS = {
    "claude": ("haiku", "sonnet"),
    "codex": ("", ""),
    "gemini": ("", ""),
    "qwen": ("", ""),
    "api": ("", ""),
    "cmd": ("", ""),
}

TITLES = {
    "claude": "Claude Code",
    "codex": "Codex (ChatGPT)",
    "gemini": "Gemini CLI",
    "qwen": "Qwen Code",
    "api": "API в формате OpenAI",
    "cmd": "своя команда",
}

LIMIT_WORDS = ("usage limit", "rate limit", "quota", "exceeded", "too many requests", "429",
               "лимит", "insufficient", "billing")

TIMEOUT = 600


class LLMError(Exception):
    """Нейросеть не ответила. limit=True — похоже на исчерпанный лимит подписки."""

    def __init__(self, text, limit=False):
        super().__init__(text)
        self.limit = limit


def _is_limit(text):
    low = (text or "").lower()
    return any(w in low for w in LIMIT_WORDS)


def _available(name):
    """Путь/описание, если способ доступен на этой машине, иначе None."""
    if name in ("claude", "codex", "gemini", "qwen"):
        return config.find_bin(name, "LOVEC_%s_BIN" % name.upper())
    if name == "api":
        base = config.get("LOVEC_API_BASE")
        return base if base and config.get("LOVEC_API_MODEL") else None
    if name == "cmd":
        return config.get("LOVEC_LLM_CMD") or None
    return None


def choose():
    """(способ, путь-или-описание) или (None, причина)."""
    explicit = (config.get("LOVEC_LLM") or "").strip().lower()
    if explicit:
        if explicit not in BACKENDS:
            return None, "LOVEC_LLM=%s — такого способа нет (есть: %s)" % (explicit, ", ".join(BACKENDS))
        where = _available(explicit)
        if not where:
            return None, "выбрано %s, но оно не найдено/не настроено" % TITLES[explicit]
        return explicit, where
    for name in AUTO_ORDER:
        where = _available(name)
        if where:
            return name, where
    return None, "не нашёл ни одной нейросети: нет claude, codex, gemini, qwen, не задан API или своя команда"


def model_for(backend, tier):
    """tier: 'bulk' (массовый разбор) или 'hot' (горячие, нужен хороший заход)."""
    key = "LOVEC_MODEL_BULK" if tier == "bulk" else "LOVEC_MODEL_HOT"
    explicit = config.get(key)
    if explicit:
        return explicit
    if backend == "api":
        return config.get("LOVEC_API_MODEL") or ""
    bulk, hot = DEFAULT_MODELS.get(backend, ("", ""))
    return bulk if tier == "bulk" else hot


def _sandbox():
    """Пустая папка вне комплекта: чтобы нейросеть не подтянула инструкции (CLAUDE.md, AGENTS.md)
    ни из комплекта, ни из офиса человека."""
    p = Path(tempfile.gettempdir()) / "lovec-sandbox"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _run(cmd, prompt, cwd):
    try:
        res = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=TIMEOUT, cwd=str(cwd))
    except subprocess.TimeoutExpired:
        raise LLMError("нейросеть не ответила за %d минут" % (TIMEOUT // 60))
    except OSError as e:
        raise LLMError("не запустилась программа %s: %s" % (cmd[0], e))
    return res


def _cli(backend, path, prompt, model):
    sb = _sandbox()
    out_file = None
    if backend == "claude":
        cmd = [path, "-p", "--tools", "", "--no-session-persistence",
               "--disable-slash-commands", "--setting-sources", "user"]
        if model:
            cmd += ["--model", model]
    elif backend == "codex":
        fd, out_file = tempfile.mkstemp(prefix="lovec-codex-", suffix=".txt")
        os.close(fd)
        cmd = [path, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
               "--color", "never", "-o", out_file]
        # Личный ~/.codex/config.toml часто содержит модель, которой нет на тарифе человека
        # (видели: gpt-5.4-mini на аккаунте ChatGPT), и хуки, которые здесь не нужны. Вход в
        # аккаунт лежит отдельно (auth.json) и сохраняется. LOVEC_CODEX_USER_CONFIG=1 — взять конфиг.
        if config.get("LOVEC_CODEX_USER_CONFIG") != "1":
            cmd.append("--ignore-user-config")
        effort = config.get("LOVEC_CODEX_EFFORT") or "low"
        if effort != "default":
            cmd += ["-c", "model_reasoning_effort=%s" % effort]
        if model:
            cmd += ["-m", model]
        cmd.append("-")
    else:  # gemini, qwen: задание в stdin, короткая строка в -p лишь запускает неинтерактивный режим
        cmd = [path, "-p", "Follow the instructions above and answer with JSON only."]
        if model:
            cmd += ["-m", model]
    try:
        res = _run(cmd, prompt, sb)
        out = res.stdout or ""
        if out_file and Path(out_file).exists():
            out = Path(out_file).read_text(encoding="utf-8", errors="replace") or out
    finally:
        if out_file:
            try:
                os.unlink(out_file)
            except OSError:
                pass
    if not out.strip():
        err = (res.stderr or "").strip()
        raise LLMError("пустой ответ: " + err[-300:], limit=_is_limit(err))
    return out


def _api(prompt, model):
    base = (config.get("LOVEC_API_BASE") or "").rstrip("/")
    key = config.get("LOVEC_API_KEY") or ""
    if not model:
        raise LLMError("не задана модель: LOVEC_API_MODEL")
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.2}).encode("utf-8")
    req = urllib.request.Request(base + "/chat/completions", data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": "Bearer " + key} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")[:300]
        raise LLMError("API ответил %d: %s" % (e.code, text), limit=e.code in (402, 429) or _is_limit(text))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise LLMError("API недоступен: %s" % e)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise LLMError("API вернул непонятный ответ: %s" % str(data)[:300])


def _cmd(prompt):
    raw = config.get("LOVEC_LLM_CMD") or ""
    cmd = shlex.split(raw, posix=not config.IS_WINDOWS)
    if config.IS_WINDOWS:   # в режиме Windows shlex оставляет кавычки внутри: "C:\\...\\python.exe"
        cmd = [c[1:-1] if len(c) > 1 and c[0] == c[-1] and c[0] in "\"'" else c for c in cmd]
    if not cmd:
        raise LLMError("LOVEC_LLM_CMD пуст")
    res = _run(cmd, prompt, _sandbox())
    if not (res.stdout or "").strip():
        err = (res.stderr or "").strip()
        raise LLMError("пустой ответ: " + err[-300:], limit=_is_limit(err))
    return res.stdout


def ask(prompt, tier="bulk"):
    """Отправить задание выбранной нейросети и вернуть текст ответа. Ошибка — LLMError."""
    backend, where = choose()
    if not backend:
        raise LLMError(where)
    model = model_for(backend, tier)
    if backend in ("claude", "codex", "gemini", "qwen"):
        return _cli(backend, where, prompt, model)
    if backend == "api":
        return _api(prompt, model)
    return _cmd(prompt)


def describe():
    backend, where = choose()
    if not backend:
        return {"ok": False, "backend": None, "detail": where}
    return {"ok": True, "backend": backend, "title": TITLES[backend], "where": where,
            "bulk": model_for(backend, "bulk") or "по умолчанию", "hot": model_for(backend, "hot") or "по умолчанию"}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    info = describe()
    if cmd == "status":
        if "--json" in sys.argv:
            print(json.dumps(info, ensure_ascii=False))
        elif info["ok"]:
            print("✅ оценивает: %(title)s (%(where)s) · модели: разбор — %(bulk)s, горячие — %(hot)s" % info)
        else:
            print("⛔ " + info["detail"])
        return 0 if info["ok"] else 1
    if cmd == "test":
        if not info["ok"]:
            print("⛔ " + info["detail"])
            return 1
        try:
            out = ask('Ответь строго JSON-массивом [{"id":"0","score":50}] и ничего больше.', "bulk")
        except LLMError as e:
            print(("⛔ лимит подписки: " if e.limit else "⛔ ") + str(e))
            return 1
        ok = "[" in out and "]" in out
        print(("✅ %s отвечает" % info["title"]) if ok else "⚠️ ответ не похож на JSON: " + out[:200])
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
