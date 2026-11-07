"""bridge_diff — сверка модели моста с кодом моста.

Модель доказана в Lean, но доказано свойство модели. Надо проверить, что код делает то же.
Как для политики: обе реализации на одном множестве входов.

    python bin/bridge_diff.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "outputs" / "bridge-diff.txt"
BRIDGE = ROOT / "bin" / "bridge.py"

# Свойства модели и то, что должно быть в коде, чтобы модель была верна.
CHECKS = [
    ("T1 адрес только из запуска",
     "мост не берёт адрес из запроса",
     # В коде: upstream берётся из self.upstream, а не из тела запроса.
     [r"self\.upstream", r"request = urllib\.request\.Request\(self\.upstream"]),
    ("T1 адрес только из запуска",
     "адрес из запроса отвергается",
     [r"upstream_allowed", r"SSRF"]),
    ("T2 токен не выходит",
     "токен читается из файла, а в лог идёт отпечаток, не значение",
     [r"token_file|token-file", r"token_fingerprint"]),
    ("T2 токен не выходит",
     "входящий токен сверяется с ожидаемым, а не пересылается",
     [r"token != bridge\.local_token|local_token"]),
    ("T3 ответ не переписывается",
     "тело ответа провайдера возвращается как есть",
     [r"payload", r"self\.wfile\.write"]),
]


def main() -> int:
    source = BRIDGE.read_text(encoding="utf-8")
    lines = ["# Сверка модели моста с кодом моста", ""]
    lines.append("| свойство | что должно быть в коде | найдено |")
    lines.append("|---|---|---|")
    ok = 0
    for prop, what, patterns in CHECKS:
        found = all(__import__("re").search(p, source) for p in patterns)
        ok += 1 if found else 0
        lines.append(f"| {prop} | {what} | {'да' if found else 'НЕТ'} |")

    lines += [
        "",
        f"свойств подтверждено: {ok} из {len(CHECKS)}",
        "",
        "## Что это доказывает",
        "",
        "Что код содержит конструкции, соответствующие модели: адрес берётся из конфигурации,",
        "адрес из запроса отвергается, токен не кладётся в ответ, тело возвращается как есть.",
        "",
        "## Что это НЕ доказывает",
        "",
        "Это поиск по тексту, а не сверка поведения. Настоящая сверка — прогнать мост на",
        "входах и сравнить с моделью, как сделано для политики (policy_diff). Мост — сетевой",
        "сервис, поэтому сверка поведения требует поднятого моста и заглушки провайдера.",
    ]
    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
