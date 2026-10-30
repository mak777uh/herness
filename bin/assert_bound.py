"""Проверка границы: команда падает, если метрика вышла за предел.

Зачем: числа в утверждениях сейчас проверяются подстрокой — сломался замер, а утверждение зелёное.
Здесь граница проверяется исполнением: запускаем команду, берём метрику, сравниваем с пределом.

Метрики:
  time   — время настенных часов, секунды
  json   — число по пути в JSON, который печатает команда (например, steps)

Пример:
  python bin/assert_bound.py --metric time --max 180 --runs 1 -- python bin/hs.py gates
  python bin/assert_bound.py --metric json --path steps --max 6 --runs 2 -- python bin/_emit.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


def run_once(command: list[str], timeout: int) -> tuple[float, str, int]:
    started = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                               encoding="utf-8", errors="replace")
    elapsed = time.perf_counter() - started
    return elapsed, completed.stdout, completed.returncode


def extract_json(stdout: str, path: str) -> float | None:
    """Ищет в выводе JSON-объект и достаёт число по пути."""
    for start in range(len(stdout)):
        if stdout[start] != "{":
            continue
        depth = 0
        for end in range(start, len(stdout)):
            if stdout[end] == "{":
                depth += 1
            elif stdout[end] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(stdout[start:end + 1])
                    except json.JSONDecodeError:
                        break
                    current = data
                    for part in path.split("."):
                        if not isinstance(current, dict) or part not in current:
                            current = None
                            break
                        current = current[part]
                    if isinstance(current, (int, float)):
                        return float(current)
                    break
    return None


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print("нужно: -- <команда>", file=sys.stderr)
        return 2
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1:]

    metric = "time"
    maximum = 0.0
    runs = 1
    path = ""
    timeout = 600
    index = 0
    while index < len(options):
        option = options[index]
        if option == "--metric":
            metric = options[index + 1]
            index += 2
        elif option == "--max":
            maximum = float(options[index + 1])
            index += 2
        elif option == "--runs":
            runs = int(options[index + 1])
            index += 2
        elif option == "--path":
            path = options[index + 1]
            index += 2
        elif option == "--timeout":
            timeout = int(options[index + 1])
            index += 2
        else:
            index += 1

    if not maximum:
        print("нужен --max", file=sys.stderr)
        return 2

    observed: list[float] = []
    failures = 0
    for _ in range(runs):
        elapsed, stdout, code = run_once(command, timeout)
        if code != 0:
            failures += 1
            print(f"команда вернула {code}")
            continue
        if metric == "time":
            observed.append(round(elapsed, 1))
        elif metric == "json":
            value = extract_json(stdout, path) if path else None
            if value is None:
                print(f"не нашёл число по пути {path!r} в выводе", file=sys.stderr)
                return 2
            observed.append(value)
        else:
            print(f"неизвестная метрика {metric}", file=sys.stderr)
            return 2

    if not observed:
        print(f"bound_failed metric={metric} max={maximum} наблюдений нет")
        return 1

    worst = max(observed)
    ok = worst <= maximum and failures == 0
    print(f"bound metric={metric} max={maximum} observed={observed} worst={worst} "
          f"{'ok' if ok else 'превышено'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
