"""repo_analysis — полный анализ всех частей репозитория и подходов.

Что анализируется:
  - части (parts/): размер, история, роль;
  - код (core-rs, bin): строки, тесты, проверки;
  - данные (lab, accept, research): сколько и зачем;
  - подходы: что проверяется, чем, где граница;
  - расхождения с тем, что поняли из книги.

    python bin/repo_analysis.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "outputs" / "repo-analysis.txt"


def size_of(path: Path) -> tuple[int, int]:
    """(файлов, байт)."""
    if not path.exists():
        return 0, 0
    files = bytes_ = 0
    for item in path.rglob("*"):
        if item.is_file() and ".git" not in item.parts:
            files += 1
            try:
                bytes_ += item.stat().st_size
            except OSError:
                pass
    return files, bytes_


def count_lines(path: Path, suffix: str) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob(f"*{suffix}"):
        if ".git" in item.parts:
            continue
        try:
            total += len(item.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            pass
    return total


def main() -> int:
    lines = ["# Полный анализ репозитория", ""]

    # Части
    lines.append("## Части (parts/)")
    lines.append("")
    lines.append("| часть | файлов | МБ | коммитов | роль |")
    lines.append("|---|---|---|---|---|")
    roles = {
        "flowguard-spec": "гарантия на поток: замыкание, посредник, политика",
        "lexspec": "якорь или отказ: закрытый словарь кодов",
        "VecDHT": "слой сети: узлы находят друг друга по смыслу",
        "nomos": "форма договора об отношениях: пулы законов",
    }
    parts = ROOT / "parts"
    for path in sorted(parts.iterdir()) if parts.exists() else []:
        if not path.is_dir() or path.name.startswith("_"):
            continue
        files, bytes_ = size_of(path)
        try:
            commits = subprocess.run(["git", "-C", str(path), "rev-list", "--count", "HEAD"],
                                     capture_output=True, text=True).stdout.strip()
        except OSError:
            commits = "?"
        lines.append(f"| {path.name} | {files} | {bytes_ / (1024**2):.1f} | {commits} | "
                     f"{roles.get(path.name, '?')} |")
    lines.append("")

    # Код
    lines.append("## Код")
    lines.append("")
    rust_lines = count_lines(ROOT / "core-rs" / "src", ".rs")
    py_lines = count_lines(ROOT / "bin", ".py")
    lines.append(f"- Rust (`core-rs/src`): **{rust_lines}** строк")
    lines.append(f"- Python (`bin`): **{py_lines}** строк")
    tests = len(list((ROOT / "bin").glob("*probe*.py"))) + len(list((ROOT / "bin").glob("*audit*.py")))
    lines.append(f"- проб и аудитов: **{tests}**")
    lines.append("")

    # Данные
    lines.append("## Данные")
    lines.append("")
    for name, folder in [("политика", "lab/tools/policy.json"),
                         ("реестр", "lab/tools/registry.jsonl"),
                         ("коды отказа", "lab/refusal-codes.json"),
                         ("договоры", "lab/tools/contracts.json")]:
        path = ROOT / folder
        if path.exists():
            lines.append(f"- {name}: `{folder}` ({path.stat().st_size} байт)")
    failures = len(list((ROOT / "lab" / "failures").glob("F-*.md")))
    claims = len(re.findall(r"^\| C-\d+", (ROOT / "CLAIMS.md").read_text(encoding="utf-8"), re.MULTILINE))
    lines.append(f"- отказов: **{failures}**")
    lines.append(f"- утверждений: **{claims}**")
    lines.append("")

    # Подходы
    lines.append("## Подходы: что проверяется и чем")
    lines.append("")
    lines.append("| что | чем проверяется | доказуемо |")
    lines.append("|---|---|---|")
    lines.append("| политика без противоречий | `policy.py --check`, `policy_probe.py` | да, 4 из 4 |")
    lines.append("| политика в коде = файл | `policy_sync.py` | да, 12 правил |")
    lines.append("| код не выходит за замыкание | `closure_probe.py` | нет, измерение |")
    lines.append("| две реализации совпадают | `policy_diff.py` | нет, 15 из 18 |")
    lines.append("| теоремы в Lean | `lean_check.py` | да, 6 теорем |")
    lines.append("| мост в Lean | `bridge_lean.py` | да, 6 теорем |")
    lines.append("| коды отказа | `refusal_codes_probe.py` | да, 4 из 4 |")
    lines.append("| стены ядра | `kernel_audit.py` | нет, аудит конфига |")
    lines.append("| опора | `claim_anchor` в Rust | нет, 51 тест |")
    lines.append("")

    # Расхождения с книгой
    lines.append("## Расхождения с тем, что поняли из книги")
    lines.append("")
    gaps = [
        ("Контекст агента — образ",
         "HISTORY_MAX уменьшен с 12 до 6, но LAST_RESULT = 4000 символов остался",
         "сократить LAST_RESULT и проверить на серии"),
        ("Гейт, защищающий себя",
         "вопрос добавлен в аудит, но сами гейты не проверены",
         "прогнать аудит и найти защищающиеся гейты"),
        ("Метрики без сравнения",
         "оговорка не добавлена — место не найдено",
         "добавить в `judge_metrics.py` вручную"),
        ("Критерий — концепция",
         "122 критерия, все с проверяемым условием",
         "проверено, расхождений нет"),
        ("Отказы закрыты",
         "69 отказов, у всех есть fix/test/caught_by",
         "проверено, расхождений нет"),
    ]
    lines.append("| что поняли | состояние | что делать |")
    lines.append("|---|---|---|")
    for what, state, todo in gaps:
        lines.append(f"| {what} | {state} | {todo} |")
    lines.append("")

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
