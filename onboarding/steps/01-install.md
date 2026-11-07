# Шаг 1 — установка (doctor: `python`, `deps`, `llm`)

**Цель:** рабочее окружение, заготовки в `data/` и найденная нейросеть для оценки. Делаешь ты.

## Что делаешь

Mac / Linux:

```bash
cd <КОМПЛЕКТ> && python3 setup.py
```

Windows (PowerShell или командная строка):

```powershell
cd <КОМПЛЕКТ>; py setup.py
```

Нет `py` — `python setup.py`. Создаёт `venv/`, ставит Телетон (библиотека для Телеграма), кладёт в
`data/` три заготовки: `niche.md` (профиль ниши), `phrases.txt` (поисковые фразы), `.env` (настройки и
ключи). `data/` в git не попадает: там всё личное. В конце печатает путь к Python ловца: это и есть `<PY>`.

Сразу после установки запиши `data/setup-state.md`: офис (путь или «нет»), система (Windows/Mac/Linux)
и чем `<PY>`, правила офиса из шага 0 одной-двумя строками, дата. Формат свободный, главное: офис, как
выдавать человеку команды, где он вводит команды, его ответы про нишу и город/регион клиентов. Если
сессия прервётся, следующий заход начнётся с этого файла и с `doctor.py`, а не с нуля.

Проверка: `<PY> lovec/doctor.py --offline` → пункты `python`, `deps` зелёные.

## Нейросеть для оценки (doctor: `llm`)

Ловец сам ищет, какая нейросеть есть на компьютере, и берёт первую найденную: Claude Code → Codex →
Gemini CLI → Qwen Code → API → своя команда. Посмотреть, что выбрано: `<PY> lovec/llm.py status`,
проверить, что она отвечает: `<PY> lovec/llm.py test`.

**Ты сам и есть нейросеть человека.** Работаешь в Claude Code — оценивать будет Claude, в Codex —
Codex, ничего ставить не надо. Если `llm` красный, значит программа не видна из окружения ловца:
найди путь (`command -v codex` / на Windows `where codex`) и впиши его:
`<PY> lovec/envset.py LOVEC_CODEX_BIN <путь>` (для Claude — `LOVEC_CLAUDE_BIN`, Gemini — `LOVEC_GEMINI_BIN`).

Если у человека несколько нейросетей и он хочет конкретную: `<PY> lovec/envset.py LOVEC_LLM codex`
(варианты: `claude`, `codex`, `gemini`, `qwen`, `api`, `cmd`).

| Что есть у человека | Как подключить |
|---|---|
| подписка Claude (Claude Code) | ничего, найдётся сам. Модели: разбор `haiku`, горячие `sonnet` |
| подписка ChatGPT (Codex) | ничего, найдётся сам; Codex должен быть залогинен (`codex login`). Модель — по умолчанию для его тарифа |
| аккаунт Google (Gemini CLI) | ничего, найдётся сам, если Gemini CLI установлен и вошёл |
| ключ API любого сервиса в формате OpenAI: OpenAI, DeepSeek, OpenRouter, Polza, Groq и др. | ниже, «Через API» |
| нейросеть на своём компьютере (Ollama, LM Studio) | «Через API», адрес `http://localhost:11434/v1` (Ollama) или `http://localhost:1234/v1` (LM Studio), ключ не нужен |
| что-то другое со своей командой | `<PY> lovec/envset.py LOVEC_LLM cmd` и `<PY> lovec/envset.py LOVEC_LLM_CMD "<команда>"`: команда получает задание в stdin и печатает ответ |

### Через API

Адрес и модель не секреты, пишешь сам:

```bash
<PY> lovec/envset.py LOVEC_LLM api
<PY> lovec/envset.py LOVEC_API_BASE https://api.deepseek.com/v1
<PY> lovec/envset.py LOVEC_API_MODEL deepseek-chat
```

Ключ — секрет, его вводит человек скрытым вводом: `<PY> lovec/secret.py LOVEC_API_KEY`. Адреса:
OpenAI `https://api.openai.com/v1`, DeepSeek `https://api.deepseek.com/v1`, OpenRouter
`https://openrouter.ai/api/v1`, Polza `https://api.polza.ai/api/v1`. Название модели человек берёт в
кабинете своего сервиса; для массового разбора подходит недорогая. Можно задать разные модели для
разбора и для горячих: `LOVEC_MODEL_BULK` и `LOVEC_MODEL_HOT`.

Проверка: `<PY> lovec/llm.py test` → `✅ … отвечает`.

## Если что-то пошло не так

| Что видно | Что значит | Что делать |
|---|---|---|
| `py`/`python3` не найден, «старше 3.9» | на машине нет подходящего Python | человек ставит Python 3.9+: Windows — с python.org (галочка «Add python.exe to PATH») или `winget install Python.Python.3.12`; Mac — `brew install python` или с python.org; Ubuntu — `sudo apt install python3 python3-venv` |
| «не создалось окружение… python3-venv» | на Debian/Ubuntu нет модуля venv | `sudo apt install python3-venv` — нужны права администратора; сначала проверь, есть ли они, и скажи честно, если не уверен |
| pip не может скачать пакеты | нет интернета или он закрыт | проверь доступ к https://pypi.org; прокси/VPN — задача человека |
| `llm` красный, «не нашёл ни одной нейросети» | ни одной программы не видно и API не задан | см. раздел выше; если ты работаешь в Claude Code или Codex, найди путь к нему и впиши |
| `llm.py test`: «лимит подписки» | кончился лимит тарифа | ловец не сломается: найденное подождёт следующего прогона. Можно подключить вторую нейросеть через `LOVEC_LLM` |
| Codex: «model is not supported when using Codex with a ChatGPT account» | в настройках модель, которой нет на тарифе | ловец по умолчанию запускает Codex без личных настроек; если всё же видно — `<PY> lovec/envset.py LOVEC_MODEL_BULK <модель с его тарифа>` или убрать `LOVEC_CODEX_USER_CONFIG` |

## Что сказать про лимит подписки

Оценка идёт в той же подписке, что и работа человека с нейросетью. Расход небольшой: сначала грубый
фильтр без нейросети отсеивает всё, что не похоже на запрос, потом пачки по 15 сообщений, не больше 150
оценок за прогон. С Claude массовый разбор делает мелкая модель (haiku), а сильная (sonnet)
подключается только для горячих, чтобы написать заход. Если лимит кончится, ловец не сломается:
найденное подождёт следующего прогона, а человеку придёт одна тревога в сутки.

Дальше: смотри `next` в doctor.
