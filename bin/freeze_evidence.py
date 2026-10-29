"""freeze_evidence — выжимка прогона в git, чтобы утверждение было проверяемо на чистом клоне.

`runs/` в git не едет (там мегабайты). Но утверждение не должно висеть в воздухе: из журнала
берётся маленькая выжимка — статус, число шагов, ключевые строки, дайджест events.jsonl — и кладётся
в `research/evidence/<run>.json`. Утверждения ссылаются сюда.

    python bin/freeze_evidence.py runs/20261029T201912-live ...
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "evidence"


def freeze(run_dir: Path) -> dict:
    events_path = run_dir / "events.jsonl"
    digest = hashlib.sha256(events_path.read_bytes()).hexdigest() if events_path.exists() else ""
    calls: list[str] = []
    answers: list[str] = []
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            payload = event.get("payload") or {}
            if kind == "tool/call":
                args = payload.get("arguments") or {}
                calls.append(f"{payload.get('name')}: {str(args)[:120]}")
            elif kind == "assistant/message":
                text = (payload.get("text") or "").strip()
                if text:
                    answers.append(text[:600])

    report = run_dir / "report.md"
    steps = len(calls)
    return {
        "run": run_dir.name,
        "events_sha256": digest,
        "tool_calls": steps,
        "calls": calls[:12],
        "answer": answers[-1] if answers else "",
        "report_excerpt": (report.read_text(encoding="utf-8")[:400] if report.exists() else ""),
        "note": "выжимка прогона; полный журнал остаётся вне git",
    }


def main(argv: list[str]) -> int:
    if not argv:
        print("укажите каталоги прогонов", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    for arg in argv:
        run_dir = (ROOT / arg).resolve() if not Path(arg).is_absolute() else Path(arg)
        if not run_dir.is_dir():
            print(f"нет каталога {arg}", file=sys.stderr)
            continue
        data = freeze(run_dir)
        path = OUT / f"{run_dir.name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{path.name}: шагов {data['tool_calls']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
