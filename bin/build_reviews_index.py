"""Индекс рецензий: собирается из файлов, руками не правится (как у Morphogenesis)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "lab" / "reviews"
FIELDS = ("id", "date", "claim", "verdict", "artifact_checked", "method", "what_would_kill_it")
VERDICTS = {"upheld", "killed", "unclear"}


def parse_file(path: Path) -> dict:
    data: dict = {}
    reasons: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("  - "):
            reasons.append(line[4:].strip())
            continue
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip()
    data["reasons"] = reasons
    data["file"] = path.name
    return data


def collect() -> tuple[list[dict], list[str]]:
    entries, problems = [], []
    for path in sorted(REVIEWS.glob("*.md")):
        if path.name == "README.md":
            continue
        item = parse_file(path)
        missing = [field for field in FIELDS if not item.get(field)]
        if missing:
            problems.append(f"{path.name}: нет полей {', '.join(missing)}")
        verdict = item.get("verdict", "")
        if verdict not in VERDICTS:
            problems.append(f"{path.name}: вердикт {verdict!r} вне словаря")
        if verdict == "killed" and not item.get("reasons"):
            problems.append(f"{path.name}: killed без причин")
        if verdict == "upheld" and not item.get("artifact_checked"):
            problems.append(f"{path.name}: upheld без указания артефакта")
        entries.append(item)
    return entries, problems


def write_index(entries: list[dict]) -> Path:
    target = REVIEWS / "index.json"
    payload = {"count": len(entries),
               "by_verdict": {verdict: sum(1 for item in entries if item.get("verdict") == verdict)
                              for verdict in sorted(VERDICTS)},
               "entries": [{"id": item.get("id"), "date": item.get("date"),
                            "verdict": item.get("verdict"), "file": item.get("file")}
                           for item in entries]}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return target


def main() -> int:
    entries, problems = collect()
    target = write_index(entries)
    counts = {verdict: sum(1 for item in entries if item.get("verdict") == verdict)
              for verdict in sorted(VERDICTS)}
    print(f"рецензий: {len(entries)} | upheld {counts['upheld']}, killed {counts['killed']}, "
          f"unclear {counts['unclear']}")
    for problem in problems:
        print(f"[FAIL] {problem}")
    print(f"индекс: {target}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
