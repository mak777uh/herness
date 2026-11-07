"""preflight — поиск инструмента по имени И контракту (эксперимент E2 плана P33).

Почему оба канала: CRAFT (ICLR 2024) показывает, что удаление имени функции из поиска роняет
точность на 6,6 п.п. Контракт — второй канал, а не замена.

    python bin/preflight.py "нужно найти подстроку в файлах"
    python bin/preflight.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "lab" / "tools" / "registry.jsonl"

STOP = {"нужно", "надо", "хочу", "может", "этот", "чтобы", "какой", "файлах", "файлы", "через"}


def load() -> list[dict]:
    if not REGISTRY.exists():
        return []
    return [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]


def words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-zА-Яа-я]{3,}", text) if w.lower() not in STOP}


def find(query: str, rows: list[dict], statuses=("active",)) -> list[dict]:
    wanted = words(query)
    scored = []
    for row in rows:
        if row.get("status") not in statuses:
            continue
        name_hit = row["id"].lower() in query.lower()
        contract_words = words(row["contract"] + " " + row["returns"])
        # Основы слов: «запечатать» и «запечатывает» — одно слово для поиска.
        stems_wanted = {word[:6] for word in wanted}
        stems_contract = {word[:6] for word in contract_words}
        overlap = len(stems_wanted & stems_contract)
        if not name_hit and overlap == 0:
            continue
        # Имя весит больше: по CRAFT оно самый сильный сигнал. Общие слова («каталог», «файл»)
        # встречаются в контрактах многих инструментов и не должны перевешивать.
        # Общие основы целиком: «катало» — это «каталог», он есть почти в каждом контракте.
        common = {"катало", "файл", "строк", "текст", "содер", "возвр", "возвра"}
        overlap = len({stem for stem in stems_wanted & stems_contract} - common)
        score = (3 if name_hit else 0) + overlap
        scored.append({"id": row["id"], "score": score, "by": "имя" if name_hit else "контракт"})
    return sorted(scored, key=lambda item: -item["score"])


def self_test() -> int:
    rows = load()
    if not rows:
        print("нет реестра")
        return 2
    cases = [
        ("найти подстроку в файлах", "search", True),
        ("перечислить содержимое каталога", "list", True),
        ("запечатать файл отпечатком", "seal", True),
        ("проверить доступность адреса", "netprobe", True),
        ("отправить письмо по почте", None, False),
    ]
    lines = ["# Pre-flight: поиск по имени и контракту", ""]
    ok_count = 0
    for query, expected, should_find in cases:
        found = find(query, rows)
        top = found[0]["id"] if found else None
        ok = (top == expected) if should_find else (top is None)
        ok_count += 1 if ok else 0
        lines.append(f"{query:34} → {top or 'ничего':10} {'ok' if ok else 'ПРОВАЛ'}")
    lines += ["", f"верно: {ok_count} из {len(cases)}"]
    text = "\n".join(lines) + "\n"
    (ROOT / "research" / "outputs" / "preflight-check.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0 if ok_count == len(cases) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="pre-flight поиск инструмента")
    parser.add_argument("query", nargs="?", default=None)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--include-archived", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.self_test:
        return self_test()
    if not args.query:
        print("нужно: bin/preflight.py \"<что нужно сделать>\"", file=sys.stderr)
        return 2
    statuses = ("active", "archived") if args.include_archived else ("active",)
    for item in find(args.query, load(), statuses):
        print(f"{item['id']:10} {item['score']:>2}  по {item['by']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
