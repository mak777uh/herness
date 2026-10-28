"""M1: журнал и артефакты. Проверяем главный инвариант — свидетельство раньше утверждения.

Запуск: python tests/test_m1_journal.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.contracts import ContractError  # noqa: E402
from core.journal import ArtifactRef, Journal  # noqa: E402
from core.loop import MockProvider, Step, run  # noqa: E402
from core.tools import ShellTool  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


def _read_events(run_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]


@case("артефакт появляется до записи результата", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal = Journal(root / "run")
        provider = MockProvider([
            Step(tool={"name": "shell", "args": {"command": "echo artifact-first"}}),
            Step(text="готово"),
        ])
        result = run("проба", provider, ShellTool(root), journal)
        assert result["status"] == "done", result

        events = _read_events(root / "run")
        types = [e["type"] for e in events]
        assert types == ["run/start", "tool/call", "tool/result", "assistant/message", "run/end"], types

        res = next(e for e in events if e["type"] == "tool/result")
        artifact = root / "run" / res["payload"]["artifact"]["path"]
        assert artifact.exists(), "артефакт не создан"
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert digest == res["payload"]["artifact"]["sha256"], "дайджест не совпал"


@case("результат без артефакта записать нельзя", True)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        with Journal(Path(tmp) / "run") as journal:
            journal.tool_result("call-1", ArtifactRef(sha256="0" * 64, path="artifacts/нет.txt", bytes=0), ok=True)


@case("подменённый артефакт отбивается", True)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        with Journal(Path(tmp) / "run") as journal:
            ref = journal.put_artifact(b"original")
            (Path(tmp) / "run" / ref.path).write_bytes(b"tampered")
            journal.tool_result("call-1", ref, ok=True)


@case("удалённый артефакт отбивается", True)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        with Journal(Path(tmp) / "run") as journal:
            ref = journal.put_artifact(b"data")
            (Path(tmp) / "run" / ref.path).unlink()
            journal.tool_result("call-1", ref, ok=True)


@case("бюджет шагов останавливает цикл", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal = Journal(root / "run")
        provider = MockProvider([Step(tool={"name": "shell", "args": {"command": "echo x"}})] * 3)
        result = run("цикл", provider, ShellTool(root), journal, max_steps=3)
        assert result["status"] == "budget", result
        assert result["steps"] == 3, result


def main() -> int:
    failed = 0
    for name, should_raise, fn in CASES:
        try:
            fn()
            raised = False
        except ContractError:
            raised = True
        ok = raised == should_raise
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    print(f"\nM1: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
