"""refusal_codes_probe — отрицательный контроль словаря кодов отказа.

Проверяем три свойства словаря:
  1. коды уникальны;
  2. у каждого кода есть значение и действие;
  3. неизвестный код отвергается, а не принимается молча.

    python bin/refusal_codes_probe.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import refusal_codes as rc  # noqa: E402

OUT = ROOT / "research" / "outputs" / "refusal-codes-probe.txt"


def main() -> int:
    lines = ["# Словарь кодов отказа: контроль", ""]
    caught = 0
    total = 0

    # 1. Уникальность.
    total += 1
    names = list(rc.VOCABULARY)
    unique = len(names) == len(set(names))
    caught += 1 if unique else 0
    lines.append(f"уникальность кодов: {'да' if unique else 'НЕТ'} ({len(names)} кодов)")

    # 2. У каждого кода есть значение и действие.
    total += 1
    complete = all(means and remedy for means, remedy in rc.VOCABULARY.values())
    caught += 1 if complete else 0
    lines.append(f"у каждого кода есть значение и действие: {'да' if complete else 'НЕТ'}")

    # 3. Неизвестный код отвергается.
    total += 1
    result = subprocess.run([sys.executable, "bin/refusal_codes.py", "--check", "NO_SUCH_CODE"],
                            cwd=str(ROOT), capture_output=True, text=True)
    rejected = result.returncode != 0
    caught += 1 if rejected else 0
    lines.append(f"неизвестный код отвергнут: {'да' if rejected else 'НЕТ'}")

    # 4. Известный код принимается.
    total += 1
    result = subprocess.run([sys.executable, "bin/refusal_codes.py", "--check", "S4_POLICY_CONFLICT"],
                            cwd=str(ROOT), capture_output=True, text=True)
    accepted = result.returncode == 0
    caught += 1 if accepted else 0
    lines.append(f"известный код принят: {'да' if accepted else 'НЕТ'}")

    lines += ["", f"проверок пройдено: {caught} из {total}"]
    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if caught == total else 1


if __name__ == "__main__":
    sys.exit(main())
