"""verify_answers — машинная проверка смысла ответа для нашего семейства задач.

Зачем: приёмка проверяет форму (опора, статус, пороги), но не то, что номер из ответа
действительно нужного типа. Для задач «найди утверждение типа X» это проверяется без человека:
читаем CLAIMS.md и сверяем тип.

Так измеряется **ложное принятие** — обратная ошибка к F-0028: прогон прошёл, а ответ неверен.

    python bin/verify_answers.py accept/<критерий>.json <журнал.bin>...
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept  # noqa: E402

CLAIMS = ROOT / "CLAIMS.md"
ROW = re.compile(r"^\|\s*(C-\d{4})\s*\|(.*)$")


def claim_types() -> dict[str, str]:
    """Номер утверждения → тип (третья колонка строки реестра)."""
    out: dict[str, str] = {}
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3:
            out[match.group(1)] = cells[2]
    return out


def expected_type(text: str) -> str | None:
    """Какой тип просили найти: ищем слово типа в тексте задачи."""
    for kind in ("statistics", "measurement", "proof", "test", "observation", "judgment"):
        if kind in text.lower():
            return kind
    return None


def answer_check(journal: Path, want: str | None, known: dict[str, str]) -> tuple[bool, str]:
    records, _tail, _problems = accept.parse_journal(journal.read_bytes())
    answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
    if not answers:
        return (False, "нет run/end")
    text = answers[-1]
    ids = re.findall(r"C-\d{4}", text)
    if not ids:
        return (False, "в ответе нет номера утверждения")
    if want is None:
        return (None, "не проверяется: в задаче не назван тип")
    stamp = ids[0]
    actual = known.get(stamp)
    if actual is None:
        return (False, f"{stamp} нет в реестре")
    ok = actual == want
    return (ok, f"{stamp}: в реестре {actual}, просили {want}")


COMMAND_HINTS = ("python ", "pwsh ", "bin/", "pytest", "bash ")


def completeness(task: str, answer: str) -> tuple[bool | None, str]:
    """Полнота ответа там, где задача требует больше одного элемента.

    Сейчас проверяется одно: если в задаче просили «команду», она обязана быть в ответе.
    Это машинно, без человека — и ровно то, чего не хватало: ответ может быть верным по типу
    и при этом неполным.
    """
    if "команд" not in task.lower():
        return (None, "не проверяется: команду не просили")
    found = any(hint in answer.lower() for hint in COMMAND_HINTS)
    return (found, "команда названа" if found else "команду просили, но в ответе её нет")


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if len(argv) < 2:
        print("verify_answers <критерий.json> <журнал.bin>...", file=sys.stderr)
        return 2
    criteria = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    # Тип берём из задачи ПРОГОНА (run/start), а не из переданного критерия: в наборе разные
    # прогоны решали разные задачи, и критерий одного из них не описывает остальные.
    def want_for(records) -> str | None:
        starts = [rest for kind, rest in accept.events(records) if kind == "run/start"]
        return expected_type(starts[-1] if starts else "")
    known = claim_types()
    rows = []
    for name in argv[1:]:
        path = Path(name)
        if not path.exists():
            continue
        records, _tail, _problems = accept.parse_journal(path.read_bytes())
        accepted, _rows = accept.check(criteria, records)
        if not accepted:
            continue  # отказы разбираются отдельно; здесь только проверка принятых
        ok, detail = answer_check(path, want_for(records), known)
        verdict = "верно" if ok else ("н/п" if ok is None else "НЕВЕРНО")
        answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
        starts = [rest for kind, rest in accept.events(records) if kind == "run/start"]
        full, full_detail = completeness(starts[-1] if starts else "",
                                         answers[-1] if answers else "")
        if full is False:
            verdict = "НЕПОЛНО"
            detail = detail + "; " + full_detail
        elif full is None:
            detail = detail + "; " + full_detail
        rows.append((path.name, verdict, detail))
    if not rows:
        print("принятых прогонов нет — проверять нечего")
        return 0
    wrong = sum(1 for _n, verdict, _d in rows if verdict in ("НЕВЕРНО", "НЕПОЛНО"))
    for name, verdict, detail in rows:
        print(f"{name:28} {verdict:8} {detail}")
    print(f"\nпринятых: {len(rows)}; неверных ответов: {wrong}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
