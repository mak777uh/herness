"""redact_secret_like — заменить в тексте строки, похожие на ключ, на описание формы.

Зачем: заметки кросс-аудита и отчёты цитируют примеры ключей. Гейт секретов обязан их видеть,
но хранить литеральный ключ в репозитории нельзя даже как пример — иначе гейт краснеет на
собственной документации, и его начинают отключать.

    python bin/redact_secret_like.py <файл> [<файл> ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bin.hs import SECRET_PATTERNS  # noqa: E402


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pattern in SECRET_PATTERNS:
        def replace(match: re.Match) -> str:
            nonlocal count
            count += 1
            body = match.group(0)
            return f"«{body[:6]}…» (форма ключа, значение не хранится)"

        text = pattern.sub(replace, text)
    return text, count


def main(argv: list[str]) -> int:
    total = 0
    for name in argv:
        path = Path(name)
        text = path.read_text(encoding="utf-8")
        cleaned, count = redact(text)
        if count:
            path.write_text(cleaned, encoding="utf-8")
        total += count
        print(f"{name}: заменено {count}")
    return 0 if total >= 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
