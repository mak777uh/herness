"""Negative controls для test-manifest: прибор обязан ловить исчезновение и нулевые тесты."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import test_manifest as tm  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def base_manifest() -> dict:
    return {
        "schema_version": "test-manifest-v1",
        "python": [{
            "id": "test_ok.py",
            "path": "tests/test_ok.py",
            "runner": "custom-main",
            "minimum_checks": 1,
        }],
        "rust": [
            {"id": "rust:lib", "runner": "cargo-test", "args": ["--lib"], "minimum_tests": 1},
            {"id": "rust:tests", "runner": "cargo-test", "args": ["--tests"], "minimum_tests": 1},
        ],
    }


def write_manifest(root: Path, manifest: dict) -> None:
    (root / "tests" / "test-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "tests").mkdir()
        suite = root / "tests" / "test_ok.py"
        suite.write_text("def main():\n    print('[ok] fake')\n\nif __name__ == '__main__':\n    main()\n",
                         encoding="utf-8")
        manifest = base_manifest()
        write_manifest(root, manifest)

        check(not tm.validate_manifest(root, manifest), "валидный минимальный manifest принимается")

        missing = copy.deepcopy(manifest)
        suite.unlink()
        check(any("нет файла" in problem for problem in tm.validate_manifest(root, missing)),
              "missing suite file даёт FAIL")
        suite.write_text("def main():\n    print('[ok] fake')\n\nif __name__ == '__main__':\n    main()\n",
                         encoding="utf-8")

        (root / "tests" / "test_extra.py").write_text("def main():\n    print('[ok] extra')\n",
                                                       encoding="utf-8")
        check(any("не зарегистрирован" in problem for problem in tm.validate_manifest(root, manifest)),
              "unregistered discovered suite даёт FAIL")
        (root / "tests" / "test_extra.py").unlink()

        duplicate = copy.deepcopy(manifest)
        duplicate["python"].append({**duplicate["python"][0], "id": "test_duplicate.py"})
        check(any("дубликат tests/test_ok.py" in problem
                  for problem in tm.validate_manifest(root, duplicate)),
              "duplicate path даёт FAIL")

        unknown = copy.deepcopy(manifest)
        unknown["python"][0]["runner"] = "mystery"
        check(any("неизвестный" in problem for problem in tm.validate_manifest(root, unknown)),
              "unknown runner даёт FAIL")

        zero = copy.deepcopy(manifest)
        zero["python"][0]["minimum_checks"] = 0
        check(any("minimum_checks" in problem for problem in tm.validate_manifest(root, zero)),
              "нулевой minimum checks даёт FAIL")

        traversal = copy.deepcopy(manifest)
        traversal["python"][0]["path"] = "../outside.py"
        check(any("выход за root" in problem for problem in tm.validate_manifest(root, traversal)),
              "path traversal даёт FAIL")

        duplicate_id = copy.deepcopy(manifest)
        duplicate_id["rust"][0]["id"] = "test_ok.py"
        check(any("дубликат 'test_ok.py'" in problem
                  for problem in tm.validate_manifest(root, duplicate_id)),
              "duplicate id между Python и Rust даёт FAIL")

        no_main = copy.deepcopy(manifest)
        suite.write_text("print('[ok] not a main')\n", encoding="utf-8")
        check(any("требует top-level main" in problem
                  for problem in tm.validate_manifest(root, no_main)),
              "custom-main без main() даёт FAIL")

        no_pytest = copy.deepcopy(manifest)
        no_pytest["python"][0].update(runner="pytest", minimum_collected=1, minimum_executed=1)
        suite.write_text("def helper():\n    return True\n", encoding="utf-8")
        check(any("не нашёл top-level test_" in problem
                  for problem in tm.validate_manifest(root, no_pytest)),
              "pytest suite без test_* даёт FAIL")

        suite.write_text("def main():\n    pass\n", encoding="utf-8")
        zero_run = tm.run_python_suite(root, manifest["python"][0], timeout=10)
        check(not zero_run.ok and zero_run.checks == 0,
              "custom-main rc=0 без markers считается zero-test FAIL")

        suite.write_text("def main():\n    print('[ok] one')\n\nif __name__ == '__main__':\n    main()\n",
                         encoding="utf-8")
        one_run = tm.run_python_suite(root, manifest["python"][0], timeout=10)
        check(one_run.ok and one_run.checks == 1,
              "custom-main с одним marker и rc=0 проходит")

        suite.write_text("def main():\n    print('[FAIL] lied')\n\nif __name__ == '__main__':\n    main()\n",
                         encoding="utf-8")
        lied_run = tm.run_python_suite(root, manifest["python"][0], timeout=10)
        check(not lied_run.ok and lied_run.returncode == 0,
              "custom-main rc=0 только с [FAIL] marker не принимается")

        suite.write_text("def main():\n    print('[ok] positive')\n    print('[FAIL] expected refusal')\n\n"
                         "if __name__ == '__main__':\n    main()\n", encoding="utf-8")
        expected_refusal = tm.run_python_suite(root, manifest["python"][0], timeout=10)
        check(expected_refusal.ok and expected_refusal.checks == 1,
              "ожидаемый [FAIL] diagnostic не ложит успешный suite")

        check(tm.PYTEST_PASSED.findall("2 passed in 0.01s\n") == ["2"]
              and tm.UNITTEST_RAN.findall("Ran 3 tests in 0.01s\n") == ["3"]
              and tm.CARGO_RESULT.findall("test result: ok. 4 passed; 0 failed;\n") == ["4"],
              "pytest/unittest/cargo counters разбираются")

        results, problems = tm.run_manifest(root, manifest, only=["missing"], timeout=10)
        check(not results and any("неизвестный selection" in problem for problem in problems),
              "unknown selection отвергается до запуска")

        rust_gap = copy.deepcopy(manifest)
        rust_gap["rust"][0]["args"] = []
        (root / "core-rs" / "src" / "bin").mkdir(parents=True)
        (root / "core-rs" / "src" / "bin" / "extra.rs").write_text("fn main() {}\n", encoding="utf-8")
        rust_problems = tm.validate_manifest(root, rust_gap)
        check(any("нет cargo-test с --lib" in problem for problem in rust_problems)
              and any("для бинаря extra нет cargo-smoke" in problem for problem in rust_problems),
              "Rust manifest требует --lib/--tests и smoke каждого бинаря")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"проверок: {len(RESULTS)}; провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
