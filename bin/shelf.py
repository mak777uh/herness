"""shelf — поиск по складу: литература, данные, харнессы, решения, отказы, ADR.

Зачем: склад бесполезен, если в него не заглядывают в момент проблемы. Правило AGENTS.md
«сначала справочник, потом изобретение» до сих пор держалось на памяти, а память подводила: три раза
за сессию механизм изобретался заново, хотя ответ лежал в складе.

    python bin/shelf.py search "выход из тупика зацикливание файл"
    python bin/shelf.py search "ложный успех приёмка" --top 5
    python bin/shelf.py stats

Поиск простой и воспроизводимый: совпадение по словам (без внешних моделей), ранжирование — число
совпавших слов и их длина. Ссылка и статус источника печатаются рядом, чтобы не перепутать
«прочитано» с «записано».
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCES = [
    "research/REFS-INDEX.md",
    "research/DATA-LINKS.md",
    "research/HARNESSES-INDEX.md",
    "docs/CATALOG.md",
    "docs/TOP-REVIEW.md",
    "NOT-CLAIMED.md",
]
GLOB_SOURCES = ["lab/failures/F-*.md", "docs/ADR-*.md", "research/outputs/*.txt"]


def lines_of(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        return []


def all_lines() -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    for name in SOURCES:
        path = ROOT / name
        for line in lines_of(path):
            if line.strip():
                chunks.append((name, line.strip()))
    for pattern in GLOB_SOURCES:
        for path in sorted(ROOT.glob(pattern)):
            for line in lines_of(path):
                if line.strip():
                    chunks.append((str(path.relative_to(ROOT)).replace("\\", "/"), line.strip()))
    ledger = ROOT / "lab" / "adoptions.json"
    if ledger.exists():
        for entry in json.loads(ledger.read_text(encoding="utf-8")):
            text = " | ".join(str(entry.get(key, "")) for key in
                              ("id", "mechanism", "source", "status", "decision", "negative_control"))
            chunks.append(("lab/adoptions.json", text))
    return chunks


def terms(query: str) -> list[str]:
    words = [word.lower() for word in re.findall(r"[\w\-]{4,}", query)]
    return sorted(set(words), key=len, reverse=True)


def score(line: str, query_terms: list[str]) -> float:
    low = line.lower()
    total = 0.0
    for term in query_terms:
        if term in low:
            total += 1 + math.log(1 + len(term))
    return total


def search(query: str, top: int) -> int:
    query_terms = terms(query)
    if not query_terms:
        print("нужен запрос длиннее трёх букв", file=sys.stderr)
        return 2
    ranked = []
    for name, line in all_lines():
        value = score(line, query_terms)
        if value > 0:
            ranked.append((value, name, line))
    ranked.sort(key=lambda item: -item[0])
    if not ranked:
        print(f"ничего не найдено по {query_terms} — это тоже результат: запиши в lab/")
        return 0
    print(f"# запрос: {query!r}; слов: {len(query_terms)}; найдено: {len(ranked)}\n")
    for value, name, line in ranked[:top]:
        print(f"[{value:.1f}] {name}")
        print(f"      {line[:220]}")
    return 0


def stats() -> int:
    chunks = all_lines()
    per_source: dict[str, int] = {}
    for name, _ in chunks:
        per_source[name] = per_source.get(name, 0) + 1
    print("# склад: строк по источникам")
    for name, count in sorted(per_source.items(), key=lambda item: -item[1]):
        print(f"{count:>5}  {name}")
    print(f"\nвсего строк: {len(chunks)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="поиск по складу источников")
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("search")
    find.add_argument("query")
    find.add_argument("--top", type=int, default=8)
    sub.add_parser("stats")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.command == "search":
        return search(args.query, args.top)
    return stats()


if __name__ == "__main__":
    sys.exit(main())
