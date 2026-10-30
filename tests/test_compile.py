"""Все скрипты bin/ и core/ должны компилироваться: ловит синтаксические поломки без запуска."""

from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    failed = 0
    files = sorted(list((ROOT / 'bin').glob('*.py')) + list((ROOT / 'core').glob('*.py')))
    for path in files:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failed += 1
            print(f'[FAIL] {path.name}: {exc.msg.splitlines()[-1][:90]}')
    print(f'\nкомпиляция: {len(files) - failed}/{len(files)} ok')
    print(f'провалов: {failed}')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
