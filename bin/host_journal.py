"""host_journal — журнал, который ведёт ХОСТ, а не комната.

Зачем: журнал в комнате пишет гость, и модель может до него дотянуться через `write`. CRC ловит
порчу, но не подделку с пересчётом. Поэтому авторитетный журнал должен жить там, куда модель не
достаёт: на хосте, за мостом. Комната присылает события по одному; хост дописывает их в свой файл
и возвращает хеш, сцепленный с предыдущим.

Формат записи (JSONL, по строке):

    {"seq": 1, "prev": "00…00", "sha256": "…", "at": "2026-11-01T…", "event": "run/start task: …"}

`sha256` считается от (prev + "\n" + event), поэтому переписать середину нельзя, не пересчитав всё
после неё. `prev` первой записи — 64 нуля.

Проверка (`verify`) пересчитывает цепочку и падает на первом расхождении: это и есть ответ на
вопрос «журнал подлинный?».
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ZERO = "0" * 64
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "runs" / "host-journal"


def record_hash(prev: str, event: str) -> str:
    return hashlib.sha256((prev + "\n" + event).encode("utf-8")).hexdigest()


def append(run: str, event: str, directory: Path | None = None) -> dict:
    """Дописать событие в хостовый журнал прогона и вернуть запись с хешем."""
    directory = directory or DEFAULT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run}.jsonl"
    seq = 1
    prev = ZERO
    if path.exists():
        last = path.read_text(encoding="utf-8").strip().splitlines()
        if last:
            tail = json.loads(last[-1])
            seq = int(tail["seq"]) + 1
            prev = str(tail["sha256"])
    entry = {
        "seq": seq,
        "prev": prev,
        "sha256": record_hash(prev, event),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        handle.flush()
    return entry


def verify(run: str, directory: Path | None = None) -> tuple[int, list[str]]:
    """Пересчитать цепочку. Возвращает (сколько записей верно, проблемы)."""
    directory = directory or DEFAULT_DIR
    path = directory / f"{run}.jsonl"
    if not path.exists():
        return (0, [f"нет хостового журнала прогона {run}"])
    prev = ZERO
    good = 0
    problems: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"строка {lineno}: не JSON")
            break
        if entry.get("prev") != prev:
            problems.append(f"строка {lineno}: prev не сходится с предыдущей записью")
            break
        expected = record_hash(prev, str(entry.get("event", "")))
        if entry.get("sha256") != expected:
            problems.append(f"строка {lineno}: хеш не сходится — запись изменена")
            break
        prev = expected
        good += 1
    return (good, problems)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print("host_journal <append|verify|get> <прогон> [событие]", file=sys.stderr)
        return 2
    action, run = argv[0], argv[1] if len(argv) > 1 else ""
    if action == "append":
        if len(argv) < 3:
            print("нужно событие", file=sys.stderr)
            return 2
        entry = append(run, argv[2])
        print(json.dumps({"seq": entry["seq"], "sha256": entry["sha256"]}))
        return 0
    if action == "verify":
        good, problems = verify(run)
        print(f"записей верно: {good}")
        for problem in problems:
            print(f"  [!] {problem}")
        return 0 if not problems else 1
    if action == "get":
        path = DEFAULT_DIR / f"{run}.jsonl"
        if not path.exists():
            print(f"нет хостового журнала прогона {run}", file=sys.stderr)
            return 1
        sys.stdout.write(path.read_text(encoding="utf-8"))
        return 0
    print(f"неизвестное действие: {action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
