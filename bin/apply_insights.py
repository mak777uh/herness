"""apply_insights — внедрить 7 предложений из разбора книги.

Каждое предложение превращается в изменение в коде или документе, а не в пожелание.

    python bin/apply_insights.py --check   # показать, что будет сделано
    python bin/apply_insights.py --run     # выполнить
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check() -> int:
    print("что будет сделано:")
    print("  1. критерии приёмки: проверка на «проверяемость»")
    print("  2. аудит гейтов: вопрос «видит или защищает»")
    print("  3. отчёты: метрика без сравнения")
    print("  4. compose_prompt: меньше контекста")
    print("  5. lab/failures: проверка «закрытости»")
    print("  6. VERIFICATION-SPEC: основание проверки")
    print("  7. внешний пользователь: запись в план")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="внедрить предложения из книги")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.check:
        return check()
    if args.run:
        print("внедрение выполняет bin/insights_impl.py")
        return 0
    print("укажи --check или --run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
