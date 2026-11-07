"""refusal_codes — закрытый словарь кодов отказа для наших гейтов.

Взято по идее из lexspec (`docs/11-REFUSAL-CODES.md`): «код никогда не используется повторно
для другого дефекта и никогда не перенумеровывается». Отказ — это находка о ВХОДЕ, а не
настроение проверяющего.

Зачем нам: сейчас гейт говорит «не прошло», и это всё. С кодом видно, ЧТО именно не прошло
и что с этим делать.

    python bin/refusal_codes.py --list        # все коды
    python bin/refusal_codes.py --check CODE  # есть ли такой код
    python bin/refusal_codes.py --build       # собрать файл
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODES = ROOT / "lab" / "refusal-codes.json"

# Код, что он значит, что делать. Коды не переиспользуются и не перенумеровываются.
VOCABULARY = {
    "C0_CANON": ("свидетельство не воспроизводится: разные байты при одном входе",
                 "пересобрать артефакт из того же входа"),
    "S1_SCHEMA": ("поле отсутствует или неверного типа",
                  "исправить документ"),
    "S2_ARTIFACT_MISSING": ("артефакта, на который ссылается утверждение, нет",
                            "создать артефакт или убрать ссылку"),
    "S2_EXPECT_MISSING": ("ожидаемое значение не найдено в артефакте",
                          "сверить утверждение с артефактом"),
    "S2_EXPECT_UNDECIDABLE": ("ожидание нельзя проверить машинно: нет числа, пути или кода",
                              "переписать ожидание в проверяемую форму"),
    "S3_ANCHOR_STALE": ("опора взята из старого результата, а не из последнего",
                        "назвать токен из последнего результата"),
    "S3_ANCHOR_ABSENT": ("опоры нет: ответ ничего не подтверждает",
                         "выполнить инструмент и сослаться на его результат"),
    "S4_POLICY_CONFLICT": ("в политике противоречие: allow и deny на один ресурс",
                           "убрать одно из правил или объявить приоритет"),
    "S4_POLICY_IMPLICIT": ("неявное разрешение: «всё, кроме» с эффектом allow",
                           "заменить на явный запрет"),
    "S4_POLICY_CYCLE": ("цикл делегирования",
                        "разорвать цикл"),
    "S4_POLICY_NOLEVEL": ("правило без уровня A/B/C",
                          "указать уровень"),
    "S5_POLICY_DRIFT": ("политика в коде разошлась с политикой в файле",
                        "синхронизировать одну из сторон"),
    "S5_IMPL_DIVERGES": ("две реализации одной функции дают разное на одном входе",
                         "найти, какая права, и исправить другую"),
    "S6_CLOSURE_BREACH": ("код выходит за объявленное замыкание",
                          "убрать вызов или расширить замыкание с причиной"),
    "S7_GATE_BLIND": ("гейт не замечает подложенный дефект",
                      "чинить гейт, а не дефект"),
    "S8_WALL_MISSING": ("стена ядра не включена и не объявлена неприменимой",
                        "включить или назвать причину"),
    "S9_PROOF_FAILED": ("доказательство не собирается",
                        "чинить доказательство"),
    "S9_PROOF_AXIOM": ("доказательство опирается на нестандартную аксиому",
                       "убрать аксиому"),
    "S9_NEGATIVE_ACCEPTED": ("ложное утверждение принято — проверка не работает",
                             "чинить проверку"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="закрытый словарь кодов отказа")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--check", metavar="КОД")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.build:
        data = {"version": 1,
                "rule": "код не переиспользуется и не перенумеровывается; отказ — о входе, а не о настроении",
                "codes": [{"code": k, "means": v[0], "remedy": v[1]}
                          for k, v in VOCABULARY.items()]}
        CODES.parent.mkdir(parents=True, exist_ok=True)
        CODES.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"записано: {CODES.relative_to(ROOT)}; кодов {len(VOCABULARY)}")
        return 0
    if args.check:
        if args.check in VOCABULARY:
            means, remedy = VOCABULARY[args.check]
            print(f"{args.check}: {means}; делать: {remedy}")
            return 0
        print(f"нет такого кода: {args.check}", file=sys.stderr)
        return 2
    if args.list:
        for code, (means, remedy) in VOCABULARY.items():
            print(f"{code}: {means}")
        return 0
    print("укажи --list, --check или --build", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
