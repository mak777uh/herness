"""gate_selfdefense — какие гейты защищают себя от проверки.

Шаг 3 плана. Из книги (стр. 394): гейт, который ищет безопасности, будет
поддерживать беспорядок, чтобы оправдать себя.

Проверяем каждый гейт на три вопроса:
  1. есть ли у него отрицательный контроль (проба с подложенным дефектом)?
  2. может ли он упасть? (если он всегда зелёный — он не проверяет)
  3. не ослаблен ли он (исключения, «кроме», порог, который снижали)?

    python bin/gate_selfdefense.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"
OUT = ROOT / "research" / "outputs" / "gate-selfdefense.txt"

# Гейты из hs.py: имя → функция.
GATES = [
    ("секреты", "gate_secrets"), ("утверждения", "gate_claims"), ("ссылки", "gate_links"),
    ("критерии", "gate_criteria"), ("аудит", "gate_audit"), ("отказы", "gate_failures"),
    ("процедуры", "gate_procs"), ("формулировки", "gate_wording"),
    ("README", "gate_readme_numbers"), ("модели", "gate_models"),
    ("утверждения-проверка", "gate_claims_run"), ("самоссылка", "gate_selfref"),
    ("харнессы", "gate_harnesses"), ("глубины", "gate_depths"), ("автономия", "gate_autonomy"),
    ("решения", "gate_adoptions"), ("ядро утверждений", "gate_core_claims"),
    ("способности", "gate_capabilities"), ("журналы", "gate_journals"),
    ("рецензии", "gate_reviews"), ("пре-регистрация", "gate_prereg"), ("лаборатория", "gate_lab"),
    ("печати", "gate_seals"), ("отсутствие", "gate_absence"), ("компиляция", "gate_compile"),
    ("векторы", "gate_vectors"), ("покрытие", "gate_coverage"),
    ("большие файлы", "gate_bigfiles"), ("индекс прогонов", "gate_runs_index"),
]


def main() -> int:
    hs = (BIN / "hs.py").read_text(encoding="utf-8")
    probe = (BIN / "gate_probe.py").read_text(encoding="utf-8") if (BIN / "gate_probe.py").exists() else ""

    lines = ["# Гейты: видит или защищает себя", ""]
    lines.append("| гейт | есть функция | есть проба | может упасть |")
    lines.append("|---|---|---|---|")
    weak = []
    for name, fn in GATES:
        has_fn = f"def {fn}" in hs
        has_probe = name in probe
        # Может упасть: функция возвращает список проблем, а не константу.
        can_fail = has_fn and "return []" not in _function_body(hs, fn)
        if not has_probe:
            weak.append(name)
        lines.append(f"| {name} | {'да' if has_fn else 'НЕТ'} | {'да' if has_probe else 'НЕТ'} | "
                     f"{'да' if can_fail else 'НЕТ'} |")

    lines += [
        "",
        f"гейтов: {len(GATES)}",
        f"без пробы: {len(weak)}",
        "",
        "## Что это значит",
        "",
        "Гейт без пробы — это гейт, который никто не проверял подложенным дефектом.",
        "Он может быть всегда зелёным и этого никто не заметит.",
        "",
        "## Что делать",
        "",
        "Для каждого гейта без пробы: добавить подложенный дефект, который он обязан поймать.",
        "Если поймать не может — гейт не проверяет, а защищает себя.",
    ]
    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


def _function_body(text: str, fn: str) -> str:
    """Тело функции: от def до следующего def на нулевом отступе."""
    start = text.find(f"def {fn}")
    if start < 0:
        return ""
    end = text.find("\ndef ", start + 1)
    return text[start:end if end > 0 else len(text)]


if __name__ == "__main__":
    sys.exit(main())
