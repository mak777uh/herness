"""Сводка Rust-тестов не врёт при падении интеграционного бинарника.

Дефект F-BRIDGE-TAINT-1 (18.11.2026): `bin/rust_tests.py` брал первое вхождение
`(\\d+) failed` из вывода cargo. При красном интеграционном тесте вывод сначала
содержит зелёный lib-бинарник «0 failed», а уже потом «2 failed». Скрипт печатал
«провалов: 0» при rc=1 — гейт красный, но объяснение ложное.

    python tests/test_rust_tests_summary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin.rust_tests import parse_results  # noqa: E402

GREEN = """\
test result: ok. 133 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
"""

RED_LIB_THEN_INTEGRATION = """\
test result: ok. 133 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
test result: FAILED. 0 passed; 2 failed; 0 ignored; 0 measured; 0 filtered out
"""

RED_TWO_BINARIES = """\
test result: FAILED. 1 passed; 3 failed; 0 ignored; 0 measured; 0 filtered out
test result: FAILED. 0 passed; 4 failed; 0 ignored; 0 measured; 0 filtered out
"""

COMPILE_ERROR = "error[E0425]: cannot find value `x` in this scope\n"


def main() -> int:
    checks = [
        ("зелёный вывод", parse_results(GREEN), (136, 0)),
        ("lib зелёный, интеграционный красный", parse_results(RED_LIB_THEN_INTEGRATION), (133, 2)),
        # passed считается только по строкам `test result: ok`; в красном
        # бинарнике часть тестов могла пройти, но для вердикта важен failed=7.
        ("два красных бинарника суммируются", parse_results(RED_TWO_BINARIES), (0, 7)),
        ("ошибка сборки не выдаёт себя за ноль", parse_results(COMPILE_ERROR), (0, 0)),
    ]
    failed = 0
    for name, got, expect in checks:
        ok = got == expect
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}: {got}")
    print(f"провалов: {failed}")
    if failed:
        print("ВЕРДИКТ: FAIL — сводка тестов не различает зелёный и красный бинарники")
    else:
        print("ВЕРДИКТ: PASS — провалы суммируются по всем тестовым бинарникам")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
