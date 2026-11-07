"""bridge_verify — что мост обязан гарантировать, и проверено ли это.

Мост — единственный канал наружу. Если ядро скомпрометировано, но мост цел — данные не утекут.
Значит свойства моста надо назвать и проверить, а не предполагать.

    python bin/bridge_verify.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "bin" / "bridge.py"
OUT = ROOT / "research" / "outputs" / "bridge-verify.txt"

# Свойства моста: что он обязан гарантировать и как это видно в коде.
PROPERTIES = [
    ("адрес только один",
     "мост ходит только на upstream, заданный при запуске",
     [r"upstream"]),
    ("токен не печатается",
     "ключ читается из файла и не попадает в лог и в ответ",
     [r"token_file|token-file", r"redact|mask|\*\*\*"]),
    ("тело запроса ограничено",
     "размер входящего тела ограничен",
     [r"max_|limit|MAX_"]),
    ("модель закреплена в initramfs, а не в мосте",
     "мост пересылает тело как есть; модель задаётся при сборке образа",
     [r"bridge-model"]),
    ("ответ не переписывается",
     "мост возвращает ответ провайдера как есть",
     [r"return|json"]),
]


def main() -> int:
    if not BRIDGE.exists():
        print(f"нет моста: {BRIDGE}")
        return 2
    source = BRIDGE.read_text(encoding="utf-8")
    # Свойство «модель закреплена» живёт в сборке образа, а не в мосте: ищем и там.
    initramfs = ROOT / "bin" / "make_initramfs.py"
    if initramfs.exists():
        source += "\n" + initramfs.read_text(encoding="utf-8")
    lines = ["# Мост: что обязан гарантировать и что видно в коде", ""]
    lines.append("| свойство | что значит | видно в коде |")
    lines.append("|---|---|---|")
    ok = 0
    for name, meaning, patterns in PROPERTIES:
        found = any(re.search(p, source) for p in patterns)
        ok += 1 if found else 0
        lines.append(f"| {name} | {meaning} | {'да' if found else 'НЕТ'} |")

    lines += [
        "",
        f"свойств подтверждено по коду: {ok} из {len(PROPERTIES)}",
        "",
        "## Чего это не доказывает",
        "",
        "Это поиск по тексту, а не доказательство. Свойство «адрес только один» подтверждено",
        "тем, что в коде есть `upstream`, а не тем, что другого пути нет.",
        "",
        "## Что нужно для настоящей гарантии",
        "",
        "1. Вынести мост в отдельный маленький модуль с явным интерфейсом.",
        "2. Сформулировать три теоремы: адрес только из аргументов запуска; токен не выходит",
        "   в ответ и лог; тело ответа не меняется.",
        "3. Доказать их в Lean по модели, как сделано с политикой.",
        "4. Сверить модель с кодом тем же способом: policy_diff.",
    ]
    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
