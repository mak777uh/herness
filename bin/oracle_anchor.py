"""oracle_anchor — точная модель проверки опоры на Python.

Повторяет правила `claim_anchor` из `core-rs/src/loopmod.rs`:
  - токен конкретный, если есть цифра/разделитель и длина ≥ 3, ИЛИ это число словом;
  - число словом сравнивается как цифра («Три» = «3»);
  - опора есть, если токен ответа найден в последнем результате.

Нужна, чтобы мерить ошибки проверки без прогона в комнате.

    python bin/oracle_anchor.py "3" "## Три теоремы"
"""

from __future__ import annotations

import re
import sys

NUMBER_WORDS = {
    "один": "1", "одна": "1", "одно": "1",
    "два": "2", "две": "2", "три": "3", "четыре": "4", "пять": "5",
    "шесть": "6", "семь": "7", "восемь": "8", "девять": "9", "десять": "10",
    "одиннадцать": "11", "двенадцать": "12", "тринадцать": "13",
    "четырнадцать": "14", "пятнадцать": "15",
    "двадцать": "20", "тридцать": "30", "сорок": "40", "пятьдесят": "50", "сто": "100",
}


def number_word(token: str) -> str | None:
    return NUMBER_WORDS.get(token.lower())


def normalize_token(token: str) -> str:
    digit = number_word(token)
    return digit if digit else token


def looks_specific(token: str) -> bool:
    if number_word(token) is not None:
        return True
    # Чистое число — конкретный токен независимо от длины: ответ «3» на вопрос
    # «сколько теорем» не должен отбрасываться порогом в три знака.
    if token.isdigit():
        return True
    return len(token) >= 3 and any(
        c.isdigit() or c in "/._-" for c in token
    )


def tokens(text: str) -> list[str]:
    out = []
    for part in re.split(r"[^\w/._-]+", text, flags=re.UNICODE):
        if not part or not looks_specific(part):
            continue
        out.append(part)
        if "." in part:
            stem = part.split(".", 1)[0]
            if looks_specific(stem):
                out.append(stem)
    return out


def anchor(answer: str, results: list[str]) -> str | None:
    """Опора ответа во ВСЕХ результатах прогона. None — опоры нет.

    Исправлено по замеру на 199 случаях: поиск только в последнем результате давал
    77 % ложных отказов, когда агент читал несколько файлов и отвечал по первому.
    """
    if not results:
        return None
    haystack: list[str] = []
    for text in results:
        haystack.extend(tokens(text))
    haystack_norm = [normalize_token(t) for t in haystack]
    for token in tokens(answer):
        if token in haystack or normalize_token(token) in haystack_norm:
            return token
    for token in tokens(answer):
        # Вхождение в обе стороны: «ADR-0001» и «ADR-0001-test.md» — одно имя файла.
        if any(len(c) >= 4 and (c in token or token in c) for c in haystack):
            return token
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('нужно: oracle_anchor.py "<ответ>" "<результат>"', file=sys.stderr)
        return 2
    found = anchor(argv[0], [argv[1]])
    print(f"опора: {found if found else 'НЕТ'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
