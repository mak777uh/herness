"""Тест verify_repo: числа без команды названы, пустой вход не даёт 100 %, json воспроизводим."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, message: str) -> None:
    RESULTS.append((ok, message))


def run(path: Path, *extra: str) -> tuple[int, dict | str]:
    completed = subprocess.run(
        [sys.executable, "bin/verify_repo.py", str(path), *extra],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if "--json" in extra:
        try:
            return completed.returncode, json.loads(completed.stdout)
        except json.JSONDecodeError:
            return completed.returncode, completed.stdout
    return completed.returncode, completed.stdout


# Единица счёта — строка README: она и есть утверждение. Разделители нужны, чтобы команда
# из соседнего абзаца не приклеивалась к числу (у инструмента окно ±2 строки, и это объявлено).
README = """# sample

412K downloads за месяц.

300 stars на GitHub.

12 ms на запрос.

Ничего не измерено.

Запуск: `python -m sample --check` — проверяет 48 tests.

| метрика | значение |
|---|---|
| тесты | 99 |
| скорость | 5 ms |

Ссылки не числа: [issues](https://example.com/issues?q=is%3Aissue+2024) и [PRs](https://example.com/pulls?q=is%3Apr).

```python
# 42 tests в комментарии и retries=5 в коде — не утверждения о работе
client = OpenAI(max_retries=5)
```
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "sample"
        repo.mkdir()
        (repo / "README.md").write_text(README, encoding="utf-8")

        code, data = run(repo, "--json")
        if not isinstance(data, dict):
            print("[FAIL] json не разобран:", data)
            return 1
        check(code == 0, f"rc=0 на валидном входе (получено {code})")
        # Проза: 412K downloads, 300 stars, 12 ms — без команд; 48 tests — с командой.
        # Таблицы пробовали в R2 и отменили: на пяти репозиториях табличных чисел не было.
        check(data.get("total") == 4, f"всего утверждений 4 (получено {data.get('total')})")
        check(data.get("with_command") == 1, f"с командой 1 (получено {data.get('with_command')})")
        missing = [c for c in data.get("claims", []) if not c["has_command"]]
        check(len(missing) == 3, f"без команды названы 3 (получено {len(missing)})")
        check(all("where" not in c for c in data.get("claims", [])),
              "табличного класса больше нет (R2 отменён)")
        check(data.get("broad_total", 0) >= data.get("total", 0),
              "широкий счёт не меньше строгого")
        # Числа внутри ссылок и URL — не утверждения (ловушка is%3Aissue+2024).
        check(all("%3A" not in c["text"] and "example.com" not in c["text"]
                  for c in data.get("claims", [])),
              "URL не цитируются как утверждения")
        # Блок кода не читается: «max_retries=5» — пример, а не утверждение о работе.
        check(all("max_retries" not in c["text"] for c in data.get("claims", [])),
              "блоки кода не считаются утверждениями")
        check(all(not c["text"].startswith("|") for c in data.get("claims", [])),
              "строки таблицы не попадают в отчёт")

        _code, second = run(repo, "--json")
        if isinstance(second, dict):
            first_clean = {k: v for k, v in data.items() if k != "generated_at"}
            second_clean = {k: v for k, v in second.items() if k != "generated_at"}
            check(first_clean == second_clean, "повторный прогон даёт тот же json (кроме generated_at)")
        else:
            check(False, "второй прогон не дал json")

        empty = Path(tmp) / "empty"
        empty.mkdir()
        (empty / "README.md").write_text("# empty\n\nничего не измерено\n", encoding="utf-8")
        code, data = run(empty, "--json")
        check(code == 0, "rc=0 на README без чисел")
        if isinstance(data, dict):
            check(data.get("total") == 0, "total=0 на входе без чисел")
            check(data.get("share") is None, "доля None, а не 1.0 на пустом входе")
        else:
            check(False, "пустой вход: json не разобран")

        bare = Path(tmp) / "bare"
        bare.mkdir()
        code, _ = run(bare, "--json")
        check(code == 2, f"без README rc=2 (получено {code})")

        code, _ = run(repo, "--fail-under", "0.9", "--out", str(Path(tmp) / "threshold"))
        check(code == 1, f"--fail-under 0.9 даёт rc=1 при доле 0.25 (получено {code})")

        # Квитанции: файл пишется и содержит digest входа.
        out = Path(tmp) / "out"
        code, _ = run(repo, "--out", str(out))
        receipt = out / "sample.receipt.json"
        check(receipt.exists(), "квитанция записана")
        if receipt.exists():
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            check(len(payload.get("input_sha256", "")) == 64, "в квитанции sha256 входа")
            check(payload.get("total") == 4, "в квитанции то же число утверждений")
        # Тест не должен оставлять следов в репозитории: всё пишется во временный каталог.
        check(not (ROOT / "research" / "verify" / "sample.md").exists(),
              "тест не пишет в research/verify")

    for ok, message in RESULTS:
        print(f"[{'ok' if ok else 'FAIL'}] {message}")
    failed = sum(1 for ok, _ in RESULTS if not ok)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
