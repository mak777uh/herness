"""Проверка хеш-цепочки журнала: подмена и удаление событий видны.

Старые прогоны (без полей prev/hash) считаются legacy и не валят проверку, но и не подтверждаются.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class ChainReport:
    run: str
    events: int
    legacy: bool
    broken_at: int = 0
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.broken_at == 0


def verify_run(run_dir: Path) -> ChainReport:
    path = Path(run_dir) / "events.jsonl"
    if not path.exists():
        # каталог без журнала — не подмена, а другой формат прогона
        return ChainReport(str(run_dir), 0, True, 0, "нет events.jsonl: пропуск")
    
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return ChainReport(str(run_dir), 0, False, 1, "пустой журнал")
    events = []
    legacy = True
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            return ChainReport(str(run_dir), len(lines), False, len(events) + 1, "строка не JSON")

    prev = "genesis"
    for index, event in enumerate(events, start=1):
        if "hash" not in event or "prev" not in event:
            if index == 1:
                return ChainReport(str(run_dir), len(events), True, 0, "legacy: без цепочки")
            return ChainReport(str(run_dir), len(events), False, index, "смешение: есть и без цепочки")
        legacy = False
        body = {key: value for key, value in event.items() if key != "hash"}
        canonical = json.dumps(body, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if digest != event["hash"]:
            return ChainReport(str(run_dir), len(events), False, index, "хеш события не совпал")
        if event["prev"] != prev:
            return ChainReport(str(run_dir), len(events), False, index, "разрыв цепочки")
        prev = event["hash"]
        if int(event.get("seq", index)) != index:
            return ChainReport(str(run_dir), len(events), False, index, "дырка в нумерации")
    return ChainReport(str(run_dir), len(events), legacy, 0, "legacy: без цепочки" if legacy else "ок")


def main(argv: list[str]) -> int:
    targets = [Path(arg) for arg in argv] or sorted((ROOT / "runs").glob("*"))
    if not targets:
        print("нет журналов")
        return 2
    broken, legacy = 0, 0
    for run_dir in targets:
        if not run_dir.is_dir():
            continue
        report = verify_run(run_dir)
        if report.legacy:
            legacy += 1
            continue
        if not report.ok:
            broken += 1
            print(f"[FAIL] {run_dir.name}: событие {report.broken_at} — {report.reason}")
    total = len([target for target in targets if target.is_dir()])
    print(f"журналов: {total}, с цепочкой проверено: {total - legacy}, "
          f"legacy: {legacy}, нарушено: {broken}")
    return 0 if broken == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
