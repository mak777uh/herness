"""Проверка гейта документов: ловит ли он возврат неверного числа.

Отрицательный контроль: подкладываем в CONTINUE.md число, которого нет в
файле, и гейт обязан покраснеть. Затем восстанавливаем.

    python bin/check_docs_gate.py
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "CONTINUE.md"


def run_gate() -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(ROOT / "bin" / "gate_docs.py")],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    checks: list[tuple[str, bool]] = []

    code_before, _ = run_gate()
    checks.append(("до подмены гейт зелёный", code_before == 0))

    original = DOC.read_bytes()
    try:
        text = original.decode("utf-8")
        # Возвращаем число, которого в файле нет (записей NC- 14, ставим 29).
        injected = text.replace(
            "`NOT-CLAIMED.md` — чего не утверждаем (число — в самом файле)",
            "`NOT-CLAIMED.md` — 29 записей")
        if injected == text:
            print("не удалось подложить число: шаблон не найден — это UNKNOWN")
            return 2
        DOC.write_text(injected, encoding="utf-8")
        code_after, out_after = run_gate()
        caught = code_after != 0 and "29" in out_after
        checks.append(("подложенное число 29 поймано", caught))
        if not caught:
            print("вывод гейта после подмены:")
            print(out_after[-400:])
    finally:
        DOC.write_bytes(original)

    code_restored, _ = run_gate()
    checks.append(("после восстановления снова зелёный", code_restored == 0))

    bad = 0
    for title, ok in checks:
        if not ok:
            bad += 1
        print(f"{'ok  ' if ok else 'FAIL'} {title}")
    print()
    if bad:
        print(f"[FAIL] провалено: {bad} из {len(checks)}")
        return 1
    print(f"[ok] пройдено: {len(checks)} из {len(checks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
