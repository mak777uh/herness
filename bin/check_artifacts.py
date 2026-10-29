"""check_artifacts — сверка утверждения с его свидетельством.

Нужен для утверждений, у которых нет исполняемой команды, но есть артефакт: тогда проверка —
«в этом файле действительно лежит то, на что утверждение ссылается».

    python bin/check_artifacts.py C-0017

Читает строку из CLAIMS.md, берёт колонку «артефакт» (файл или каталог прогона) и колонку
«ожидание» (регулярное выражение), ищет ожидание в свидетельстве. Выход 1, если не нашлось.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "CLAIMS.md"


def row(claim_id: str) -> dict | None:
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| " + claim_id + " |"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            return None
        return {"id": cells[0], "artifact": cells[4], "expect": cells[6].strip("`") if len(cells) > 6 else ""}
    return None


def evidence_text(artifact: str) -> str:
    """Собирает текст свидетельства: файл целиком или все файлы каталога прогона."""
    chunks: list[str] = []
    for part in re.split(r"[,;]\s*", artifact):
        candidate = (ROOT / part.strip()).resolve()
        if candidate.is_file():
            chunks.append(candidate.read_text(encoding="utf-8", errors="replace"))
        elif candidate.is_dir():
            for path in sorted(candidate.rglob("*")):
                if path.is_file() and path.suffix in {".txt", ".jsonl", ".json", ".md", ".log", ".sql"}:
                    chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def main(argv: list[str]) -> int:
    if not argv:
        print("укажите id утверждения", file=sys.stderr)
        return 2
    claim = row(argv[0])
    if claim is None:
        print(f"нет строки {argv[0]} в CLAIMS.md", file=sys.stderr)
        return 2
    pattern = claim["expect"]
    if not pattern:
        print(f"{claim['id']}: нет ожидания — сверять нечего", file=sys.stderr)
        return 1

    text = evidence_text(claim["artifact"])
    if not text:
        print(f"{claim['id']}: свидетельство не найдено ({claim['artifact']})", file=sys.stderr)
        return 1
    if re.search(pattern, text):
        print(f"{claim['id']}: ожидание {pattern!r} найдено в свидетельстве")
        return 0
    print(f"{claim['id']}: ожидание {pattern!r} НЕ найдено в свидетельстве", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
