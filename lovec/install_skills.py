#!/usr/bin/env python3
"""Встроить ловца в офис человека: поставить два скилла в <офис>/.claude/skills/.

  install_skills.py <папка-офиса> [--dry-run]

  lovec-setup  — настройка и починка (это онбординг, он остаётся в офисе навсегда)
  lovec-daily  — повседневная работа: что нового, подкрутить фразы, разобрать находку

В текстах скиллов {{LOVEC_HOME}} заменяется на настоящий путь к этому комплекту. Комплект
остаётся там, где лежит: код и данные ловца в офис не копируются. Повторный запуск обновляет
скиллы до версии комплекта.
"""
import shutil
import sys
from pathlib import Path

import config

SKILLS = {"lovec-setup": config.ROOT / "onboarding" / "SKILL.md",
          "lovec-daily": config.ROOT / "skills" / "lovec-daily" / "SKILL.md"}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if len(args) != 1:
        sys.exit(__doc__)
    office = Path(args[0]).expanduser().resolve()
    if not office.is_dir():
        sys.exit("⛔ нет такой папки: %s" % office)
    if office == config.ROOT or config.ROOT in office.parents:
        sys.exit("⛔ это папка самого комплекта, а нужна папка ОФИСА (где лежит его CLAUDE.md)")
    version = (config.ROOT / "VERSION").read_text(encoding="utf-8").strip()
    for name, src in SKILLS.items():
        dest = office / ".claude" / "skills" / name
        text = src.read_text(encoding="utf-8").replace("{{LOVEC_HOME}}", str(config.ROOT))
        print("%s %s → %s" % ("[dry-run]" if dry else "ставлю", name, dest))
        if dry:
            continue
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        (dest / "SKILL.md").write_text(text, encoding="utf-8")
        (dest / "VERSION").write_text(version + "\n", encoding="utf-8")
    if not dry:
        config.set_value("LOVEC_OFFICE", str(office))
        print("✅ скиллы установлены (версия %s), офис записан в data/.env" % version)


if __name__ == "__main__":
    main()
