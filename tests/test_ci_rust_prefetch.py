"""E-0078: locked Rust prefetch перед offline controls в CI selftest.

Запуск: python tests/test_ci_rust_prefetch.py
Windows и POSIX: 5/5 без N/A. Сеть, секреты и cargo не используются.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "gates.yml"
RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def selftest_steps(workflow: str) -> list[dict[str, str]]:
    """Достать только шаги job selftest без внешнего YAML-парсера."""
    match = re.search(r"(?ms)^  selftest:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)", workflow)
    if not match:
        return []
    chunks = re.split(r"(?m)^      - ", match.group(1))[1:]
    steps: list[dict[str, str]] = []
    for chunk in chunks:
        step: dict[str, str] = {}
        for key in ("name", "working-directory"):
            field = re.search(rf"(?m)^        {key}:\s*(.+)$", chunk)
            if field:
                step[key] = scalar(field.group(1))
        run = re.search(r"(?ms)^        run:\s*(.*?)(?=^        \S|\Z)", chunk)
        if run:
            lines = run.group(1).splitlines()
            step["run"] = "\n".join(
                line[10:] if line.startswith("          ") else line
                for line in lines
            ).strip()
        steps.append(step)
    return steps


def valid_prefetch(steps: list[dict[str, str]]) -> bool:
    selftests = [index for index, step in enumerate(steps)
                 if step.get("run") == "python bin/hs.py selftest"]
    fetches = [index for index, step in enumerate(steps)
               if step.get("run") == "cargo fetch --locked"
               and step.get("working-directory") == "core-rs"]
    return len(selftests) == 1 and len(fetches) == 1 and fetches[0] < selftests[0]


def test_current_workflow() -> None:
    steps = selftest_steps(WORKFLOW.read_text(encoding="utf-8"))
    check(valid_prefetch(steps),
          "актуальный workflow содержит ровно один locked prefetch в core-rs перед Selftest")


def test_missing_fetch_rejected() -> None:
    steps = selftest_steps(WORKFLOW.read_text(encoding="utf-8"))
    without_fetch = [step for step in steps if step.get("run") != "cargo fetch --locked"]
    check(not valid_prefetch(without_fetch), "missing fetch отвергается")


def test_late_fetch_rejected() -> None:
    steps = selftest_steps(WORKFLOW.read_text(encoding="utf-8"))
    fetches = [step for step in steps if step.get("run") == "cargo fetch --locked"]
    late = [step for step in steps if step.get("run") != "cargo fetch --locked"] + fetches
    check(not valid_prefetch(late), "late fetch после Selftest отвергается")


def test_unlocked_fetch_rejected() -> None:
    steps = selftest_steps(WORKFLOW.read_text(encoding="utf-8"))
    unlocked = [dict(step) for step in steps]
    for step in unlocked:
        if step.get("run") == "cargo fetch --locked":
            step["run"] = "cargo fetch"
    check(not valid_prefetch(unlocked), "unlocked fetch отвергается")


def test_offline_guards_preserved() -> None:
    paths = ("test_host_journal_authority.py", "test_host_journal_authority_review.py")
    guards = {}
    for name in paths:
        source = (ROOT / "tests" / name).read_text(encoding="utf-8")
        windows_guard = source.count("CARGO_NET_OFFLINE=true")
        posix_guard = source.count('"CARGO_NET_OFFLINE": "true"')
        guards[name] = (windows_guard, posix_guard)
    check(all(counts == (1, 1) for counts in guards.values()),
          f"оба host-journal suite сохраняют Windows/POSIX offline guards: {guards}")


def main() -> int:
    tests = (
        test_current_workflow,
        test_missing_fetch_rejected,
        test_late_fetch_rejected,
        test_unlocked_fetch_rejected,
        test_offline_guards_preserved,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 — ошибка чтения/парсинга тоже RED
            check(False, f"{test.__name__}: {type(exc).__name__}: {exc}")
    failed_count = 0
    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
        failed_count += 0 if flag else 1
    print(f"проверок: {len(RESULTS)}; провалов: {failed_count}")
    return 0 if failed_count == 0 and len(RESULTS) == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
