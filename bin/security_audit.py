"""security_audit — полная проверка системы на безопасность и формальную верификацию.

Отвечает на пять вопросов:
  1. какие стены в ядре есть, а каких нет;
  2. что политика проверяется и не имеет дефектов;
  3. что политика в коде совпадает с политикой в файле;
  4. что код не выходит за объявленное замыкание;
  5. что формально доказано, а что только измерено.

    python bin/security_audit.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "research" / "outputs" / "security-audit.txt"


def run(*args: str) -> tuple[int, str]:
    result = subprocess.run([sys.executable, *args], cwd=str(ROOT),
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def count_walls() -> tuple[int, int]:
    from bin import kernel_audit as ka
    ok, missing = ka.audit(ROOT / "core-rs" / "kernel" / "config-6.18.60-net")
    return len(ok), len(ka.WALLS)


def main() -> int:
    lines = ["# Аудит безопасности и формальной верификации", ""]

    walls_ok, walls_total = count_walls()
    lines.append(f"## 1. Стены ядра: {walls_ok} из {walls_total}")
    lines.append("")

    code, text = run("bin/policy.py", "--check")
    lines.append(f"## 2. Политика: {'согласована' if code == 0 else 'ЕСТЬ ПРОБЛЕМЫ'}")
    lines.append(f"   {text.strip().splitlines()[-1] if text.strip() else ''}")
    lines.append("")

    code, text = run("bin/policy_probe.py")
    caught = "4 из 4" if "4 из 4" in text else "НЕ ВСЕ"
    lines.append(f"## 3. Проверка политики ловит дефекты: {caught}")
    lines.append("")

    code, text = run("bin/policy_sync.py")
    sync = "совпадает" if code == 0 else "РАСХОЖДЕНИЕ"
    lines.append(f"## 4. Политика в коде и в файле: {sync}")
    lines.append("")

    code, text = run("bin/closure_probe.py")
    closure = "0 нарушений" if code == 0 else "ЕСТЬ НАРУШЕНИЯ"
    lines.append(f"## 5. Код против замыкания: {closure}")
    lines.append("")

    # Формальная верификация: что доказано, а что нет.
    lines.append("## 6. Формальная верификация")
    lines.append("")
    lines.append("| свойство | доказано | измерено |")
    lines.append("|---|---|---|")
    lines.append("| политика без противоречий | да, проверкой | — |")
    lines.append("| код реализует политику | нет | да, сверкой и тестами |")
    lines.append("| замыкание (нет обхода) | **нет** | да, пробами |")
    lines.append("| ядро без ошибок | **нет** | аудит конфига |")
    lines.append("| посредник соответствует политике | **нет** | да, 51 тест |")
    lines.append("")
    lines.append("Формального доказательства (Lean, SMT) в репозитории **нет**. Это следующий шаг,")
    lines.append("и он требует, чтобы сначала было что доказывать: посредник для всех инструментов.")

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
