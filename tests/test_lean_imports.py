"""Тест достижимости Lean-модулей: сирота ловится, объявленный корень — нет."""

from __future__ import annotations

import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import check_lean_imports as check  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def ok(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def make_tree(tmp: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    base = tmp / "proofs"
    for name, body in files.items():
        path = base.joinpath(*name.split(".")).with_suffix(".lean")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return base


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = make_tree(pathlib.Path(tmp), {
            "Proofs": "import Proofs.Policy\n",
            "Proofs.Policy": "theorem a : True := trivial\n",
            "Proofs.Negative": "import Proofs.Policy\n",
            "Proofs.PartBridgeNegative": "import Proofs.Policy\n",
            "Proofs.BridgeNegative": "import Proofs.Policy\n",
            "Probe": "import Proofs.Policy\n",
        })
        ok(check.problems(base) == [], "все модули достижимы — проблем нет")

        # Сирота: файл лежит, но никто его не импортирует и корнем он не объявлен.
        (base / "Proofs" / "Orphan.lean").write_text("theorem b : True := trivial\n", encoding="utf-8")
        issues = check.problems(base)
        ok(len(issues) == 1 and "Orphan" in issues[0], f"сирота названа: {issues}")

        # Новый корень объявлен — сироты больше нет.
        roots = dict(check.ROOTS)
        roots["Proofs.Orphan"] = {"why": "тест: объявлен корнем", "builder": False}
        ok(check.problems(base, roots) == [], "объявленный корень снимает замечание")

        # Отсутствующий корень — отдельная проблема, а не тишина.
        missing = dict(check.ROOTS)
        missing["Proofs.Nope"] = {"why": "тест: корня нет", "builder": False}
        issues = check.problems(base, missing)
        ok(any("Proofs.Nope" in issue for issue in issues), f"отсутствующий корень назван: {issues}")

        # Корень с требованием сборщика, которого нет в bin/, — отдельная проблема.
        unbuilt = dict(check.ROOTS)
        unbuilt["Proofs.Orphan"] = {"why": "тест: без сборщика", "builder": True}
        issues = check.problems(base, unbuilt)
        ok(any("не собирает" in issue for issue in issues), f"корень без сборщика назван: {issues}")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
