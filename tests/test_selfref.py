"""Тесты храповика самоссылочных утверждений: гейт обязан уметь падать."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import selfref  # noqa: E402

CASES: list[tuple[str, callable]] = []

SELF_RO = ("| C-9001 | пример | observation | `python bin/check_artifacts.py C-9001` | "
           "research/NOTE.md | 31.10.2026 | `что-то` |\n")
OTHER_RO = ("| C-9002 | пример | test | `python tests/test_x.py` | "
            "research/outputs/x.txt | 31.10.2026 | `провалов: 0` |\n")


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def make(tmp: Path, rows: str, baseline: list[str] | None) -> Path:
    (tmp / "CLAIMS.md").write_text(rows, encoding="utf-8")
    if baseline is not None:
        (tmp / "evidence").mkdir(parents=True, exist_ok=True)
        (tmp / "evidence" / "selfref-baseline.json").write_text(
            json.dumps({"claims": baseline}, ensure_ascii=False), encoding="utf-8")
    return tmp


@case("без базового списка гейт говорит об этом")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = make(Path(tmp), SELF_RO, None)
        issues = selfref.problems(root)
        assert len(issues) == 1 and "selfref-baseline.json" in issues[0], issues


@case("ровно текущее состояние в базе — проблем нет")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = make(Path(tmp), SELF_RO + OTHER_RO, ["C-9001"])
        assert selfref.problems(root) == []


@case("новое самоссылочное утверждение валит гейт")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = make(Path(tmp), SELF_RO + OTHER_RO, [])
        issues = selfref.problems(root)
        assert len(issues) == 1 and "C-9001" in issues[0], issues


@case("запись в базе, которая больше не самоссылочная, тоже валит гейт")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = make(Path(tmp), OTHER_RO, ["C-9001"])
        issues = selfref.problems(root)
        assert len(issues) == 1 and "убрать из базы" in issues[0], issues


@case("утверждение с машинным артефактом самоссылочным не считается")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = make(Path(tmp), OTHER_RO, [])
        assert selfref.problems(root) == []
        assert selfref.claims(root) == []


@case("битая строка реестра не считается утверждением")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = make(Path(tmp), "| C-9003 | мало | полей |\n", [])
        assert selfref.claims(root) == []
        assert selfref.problems(root) == []


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            ok_case = True
        except AssertionError:
            ok_case = False
        failed += 0 if ok_case else 1
        print(f"[{'ok' if ok_case else 'FAIL'}] {name}")
    print(f"\nсамоссылка: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
