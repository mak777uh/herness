"""insights_impl — внедрение семи предложений из разбора книги.

1. Критерии приёмки: проверка на «проверяемость».
2. Аудит гейтов: вопрос «видит или защищает».
3. Отчёты: метрика без сравнения.
4. compose_prompt: меньше контекста.
5. lab/failures: проверка «закрытости».
6. VERIFICATION-SPEC: основание проверки.
7. Внешний пользователь: запись в план.

    python bin/insights_impl.py --run
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "outputs" / "insights-applied.txt"


def step1_criteria() -> str:
    """Критерии приёмки: у каждого должно быть проверяемое условие."""
    accept = ROOT / "accept"
    total = 0
    weak = []
    for path in accept.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        total += 1
        # Проверяемое условие: есть require_status, max_steps, anchor_regex или min_objects.
        checkable = any(k in data for k in ("require_status", "max_steps", "anchor_regex",
                                            "min_objects", "must_not_call", "tools"))
        if not checkable:
            weak.append(path.name)
    return f"критериев: {total}, без проверяемого условия: {len(weak)}" + (
        f" ({', '.join(weak[:5])})" if weak else "")


def step2_gates() -> str:
    """Аудит гейтов: добавить вопрос «видит или защищает»."""
    path = ROOT / "bin" / "gate_audit.py"
    text = path.read_text(encoding="utf-8")
    if "видит или защищает" in text:
        return "вопрос уже добавлен"
    # Добавляем вопрос в описание аудита.
    text = text.replace(
        'Проверяем каждый гейт на вопрос: если агент напишет ровно то, что гейт ищет,\nпройдёт ли он? Если да — гейт проверяет текст, а не мир.',
        'Проверяем каждый гейт на два вопроса:\n'
        '  1. если агент напишет ровно то, что гейт ищет, пройдёт ли он?\n'
        '  2. этот гейт видит или защищает себя от проверки?',
    )
    path.write_text(text, encoding="utf-8")
    return "вопрос «видит или защищает» добавлен в аудит"


def step3_metrics() -> str:
    """Отчёты: метрика без сравнения."""
    path = ROOT / "bin" / "judge_metrics.py"
    text = path.read_text(encoding="utf-8")
    if "без сравнения" in text:
        return "оговорка уже есть"
    marker = 'print(f"pass@1 (по всем прогонам): {pass1:.2f}")'
    if marker in text:
        text = text.replace(
            marker,
            marker + '\n    print("# метрика показана без сравнения: сравнение создаёт образ и страх")',
        )
        path.write_text(text, encoding="utf-8")
        return "оговорка добавлена в judge_metrics"
    return "место для оговорки не найдено"


def step4_prompt() -> str:
    """compose_prompt: меньше контекста."""
    path = ROOT / "core-rs" / "src" / "loopmod.rs"
    text = path.read_text(encoding="utf-8")
    if "HISTORY_MAX: usize = 12" not in text:
        return "константа HISTORY_MAX не найдена"
    # Уменьшаем историю с 12 до 6: меньше образа, больше факта.
    text = text.replace("const HISTORY_MAX: usize = 12;", "const HISTORY_MAX: usize = 6;", 1)
    path.write_text(text, encoding="utf-8")
    return "история в промпте: 12 → 6 строк"


def step5_failures() -> str:
    """lab/failures: у каждого отказа должно быть «что это дало»."""
    failures = ROOT / "lab" / "failures"
    total = 0
    closed = 0
    for path in failures.glob("F-*.md"):
        total += 1
        text = path.read_text(encoding="utf-8")
        if re.search(r"^(fix|test|caught_by):", text, re.MULTILINE):
            closed += 1
    return f"отказов: {total}, с закрытием: {closed}"


def step6_spec() -> str:
    """VERIFICATION-SPEC: основание проверки."""
    path = ROOT / "docs" / "VERIFICATION-SPEC.md"
    text = path.read_text(encoding="utf-8")
    if "Почему проверка нужна" in text:
        return "основание уже записано"
    addition = """
## Почему проверка нужна

Не из недоверия к модели, а из её структуры: **модель работает в поле известного**.
Её знания — прошлое, её ответ — ответ памяти. Она не может выйти за своё содержание
(Кришнамурти, «The Awakening of Intelligence», стр. 27, 52, 214).

Значит проверка должна быть **вне контекста модели**: приёмка на хосте, механические
гейты, независимая реализация. Не потому, что модель плохая, а потому что она
устроена так, что не может проверить себя.

## Почему опора — из настоящего

Опора из прошлого — это память, а не подтверждение (стр. 16). Поэтому токен обязан
быть из **последнего** результата инструмента, а не из любого.

## Почему гейт не должен защищать себя

Гейт, который ищет безопасности, — это мысль, ищущая безопасности (стр. 394).
Такой гейт будет поддерживать беспорядок, чтобы оправдать себя. Аудит должен
спрашивать: «этот гейт видит или защищает?»
"""
    path.write_text(text.rstrip("\n") + "\n" + addition, encoding="utf-8")
    return "основание проверки записано в VERIFICATION-SPEC"


def step7_user() -> str:
    """Внешний пользователь: запись в план."""
    path = ROOT / "docs" / "NEXT-PLAN.md"
    text = path.read_text(encoding="utf-8") if path.exists() else "# План\n\n"
    if "внешний пользователь" in text:
        return "уже в плане"
    addition = """
## Внешний пользователь

**У нас ноль внешних пользователей.** Это не провал, а отсутствие ядра
(Кришнамурти, стр. 13–14: новое не возникает из массы любопытных, а из нескольких,
кто идёт до конца).

Задача: найти **одного** человека, который пройдёт с нами до конца одной задачи.
Это меняет оценку по рубрике полезности сильнее, чем что-либо ещё.
"""
    path.write_text(text.rstrip("\n") + "\n" + addition, encoding="utf-8")
    return "внешний пользователь записан в план"


def main() -> int:
    lines = ["# Внедрение предложений из книги", ""]
    steps = [
        ("1. Критерии приёмки", step1_criteria),
        ("2. Аудит гейтов", step2_gates),
        ("3. Метрики без сравнения", step3_metrics),
        ("4. Контекст в промпте", step4_prompt),
        ("5. Отказы и закрытие", step5_failures),
        ("6. Основание проверки", step6_spec),
        ("7. Внешний пользователь", step7_user),
    ]
    for name, fn in steps:
        try:
            result = fn()
        except Exception as error:  # noqa: BLE001
            result = f"ОШИБКА: {type(error).__name__}: {error}"
        lines.append(f"**{name}:** {result}")
        print(f"{name}: {result}")

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"\nзаписано: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
