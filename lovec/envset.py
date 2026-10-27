#!/usr/bin/env python3
"""Записать НЕсекретную настройку в data/.env:  envset.py KEY VALUE
(секреты TG_API_HASH и TG_BOT_TOKEN сюда не передают — для них set-secret.sh)."""
import sys

import config

SECRET = {"TG_API_HASH", "TG_BOT_TOKEN"}

if len(sys.argv) != 3:
    sys.exit(__doc__)
key, value = sys.argv[1], sys.argv[2]
if key in SECRET:
    sys.exit("⛔ %s — секрет: его вводит человек через set-secret.sh, не через агента" % key)
config.set_value(key, value)
print("✅ %s записан" % key)
