"""Пре-регистрация: проверка формата и поиск экспериментов без регистрации.

Правило взято у Morphogenesis: гипотеза и критерий фиксируются до запуска, а «разница между плечами»
не запускается, пока не посчитана арифметика, которая эту разницу создаёт.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "lab" / "prereg"
REQUIRED = ("id", "date", "question", "hypothesis", "criterion", "arms", "sensitivity")
REQUIRED_V2 = ("unit_of_analysis", "primary_metric", "test", "stopping_rule")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _overlay_source(data: dict, root: Path) -> tuple[Path | None, list[str]]:
    """Возвращает безопасный source path для явно помеченного correction-overlay."""
    markers = ("source_prereg", "source_prereg_sha256", "historical_frozen", "corrected_frozen")
    if not all(field in data for field in markers):
        return None, []
    raw = data.get("source_prereg")
    if not isinstance(raw, str) or not raw:
        return None, ["source_prereg отсутствует или имеет неверный тип"]
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        return None, ["source_prereg должен быть безопасным repo-relative путём"]
    candidate = (root / relative).resolve()
    try:
        parts = candidate.relative_to(root.resolve()).parts
    except ValueError:
        return None, ["source_prereg выходит за repository root"]
    if parts[:2] != ("lab", "prereg"):
        return None, ["source_prereg должен указывать внутри lab/prereg"]
    return candidate, []


def inherit_overlay(data: dict, root: Path) -> tuple[dict, list[str]]:
    """Наследует отсутствующие обязательные поля из hash-verified source prereg.

    Исходные файлы не записываются. Явные поля overlay главнее source; source сам
    должен удовлетворять своей схеме, поэтому неполный источник остаётся FAIL.
    """
    merged = dict(data)
    source_path, problems = _overlay_source(data, root)
    if source_path is None or problems:
        return merged, problems
    if data.get("schema", 1) < 2:
        return merged, problems
    expected = data.get("source_prereg_sha256")
    if not isinstance(expected, str) or not DIGEST.match(expected):
        return merged, ["source_prereg_sha256 имеет неверный формат"]
    if not source_path.is_file():
        return merged, [f"source_prereg не найден: {data.get('source_prereg')}"]
    actual = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
    if actual != expected:
        return merged, [f"source_prereg_sha256 не совпадает: {expected} != {actual}"]
    try:
        source = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return merged, [f"source_prereg не читается: {exc}"]
    if not isinstance(source, dict):
        return merged, ["source_prereg не является объектом"]
    source_required = list(REQUIRED)
    if source.get("schema", 1) >= 2:
        source_required += list(REQUIRED_V2)
    missing_source = [field for field in source_required if not source.get(field)]
    if missing_source:
        return merged, [f"source_prereg не удовлетворяет схеме: {', '.join(missing_source)}"]
    required = list(REQUIRED)
    if data.get("schema", 1) >= 2:
        required += list(REQUIRED_V2)
    for field in required:
        if not data.get(field):
            merged[field] = source[field]
    return merged, problems


def entries(prereg_dir: Path = PREREG, root: Path = ROOT) -> tuple[list[dict], list[str]]:
    items, problems = [], []
    for path in sorted(prereg_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: не JSON ({exc.msg})")
            continue
        if not isinstance(data, dict):
            problems.append(f"{path.name}: не объект")
            continue
        data, overlay_problems = inherit_overlay(data, root)
        problems.extend(f"{path.name}: {problem}" for problem in overlay_problems)
        required = list(REQUIRED)
        if data.get("schema", 1) >= 2:
            required += list(REQUIRED_V2)
        missing = [field for field in required if not data.get(field)]
        if missing:
            problems.append(f"{path.name}: нет полей {', '.join(missing)}")
        if data.get("closed") and not data.get("conclusion"):
            problems.append(f"{path.name}: закрыто без conclusion")
        data["_file"] = path.name
        items.append(data)
    return items, problems


def experiment_dirs() -> list[Path]:
    runs = ROOT / "runs"
    if not runs.exists():
        return []
    return sorted(path for path in runs.iterdir() if path.is_dir() and path.name.startswith(("exp", "batch")))


def debt(items: list[dict]) -> list[str]:
    registered = {run for item in items for run in item.get("runs", [])}
    result = []
    for directory in experiment_dirs():
        relative = f"runs/{directory.name}"
        if relative not in registered:
            result.append(relative)
    return result


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "check"
    items, problems = entries()

    if command == "debt":
        missing = debt(items)
        print(f"пре-регистраций: {len(items)} | экспериментов без регистрации: {len(missing)}")
        for path in missing[:20]:
            print(" ", path)
        return 0

    print(f"пре-регистраций: {len(items)}")
    with_sensitivity = sum(1 for item in items if item.get("sensitivity"))
    print(f"чувствительность: есть у {with_sensitivity} из {len(items)}")
    for problem in problems:
        print(f"[FAIL] {problem}")
    unclosed = [item["id"] for item in items if not item.get("closed")]
    if unclosed:
        print(f"не закрыты: {', '.join(unclosed)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
