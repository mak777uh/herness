"""Тесты карты способностей: она строится из кода и не расходится с ним."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin.gen_capabilities import build  # noqa: E402
from core.tools import GrepTool, ListTool, ReadTool, ShellTool  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


@case("у всех инструментов роутера есть meta", False)
def _():
    missing = [cls.__name__ for cls in (ShellTool, ReadTool, GrepTool, ListTool)
               if not getattr(cls, "meta", None)]
    assert not missing, missing


@case("capabilities.json совпадает с кодом", False)
def _():
    actual = json.loads((ROOT / "capabilities.json").read_text(encoding="utf-8"))
    expected = build()
    assert actual["tools"] == expected["tools"], "расходятся инструменты"
    assert actual["workflow"] == expected["workflow"], "расходятся шаги воркфлоу"


@case("каждый инструмент умеет хотя бы одно действие и объект", False)
def _():
    for tool in build()["tools"]:
        assert tool["actions"] and tool["objects"], tool


@case("все эффекты из известного набора", False)
def _():
    known = {"read", "write", "exec", "net"}
    for tool in build()["tools"]:
        assert set(tool["effects"]) <= known, tool


def main() -> int:
    failed = 0
    for name, should_raise, fn in CASES:
        try:
            fn()
            raised = False
        except AssertionError:
            raised = True
        ok = raised == should_raise
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    print(f"\nспособности: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
