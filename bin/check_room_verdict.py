"""Проверка исправления F-ROOM-1: пустой ответ не может быть PASS.

Зачем отдельный файл: дефект был не в комнате, а в чтении её результата.
Проверка должна ловить именно его — ложный PASS при пустом ответе — и при
этом принимать правильный PASS с ответом (положительный контроль).

    python bin/check_room_verdict.py            # прогон
    python bin/check_room_verdict.py --self-test  # то же, плюс проверка самого теста

Отрицательный контроль не пустой: подложены три реалистично похожих случая,
которые НЕ должны считаться PASS, и один, который должен.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin" / "lib" / "index.js"
NODE = "node"


def run_node(script: str) -> tuple[int, str]:
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def check_settle() -> tuple[bool, list[str]]:
    """Вердикт: пустой ответ никогда не PASS; ответ с текстом — как объявлено."""
    script = f"""
import {{ settleVerdict }} from {json.dumps(PLUGIN.as_uri())};
const cases = [
  // [объявлено, ответ, ожидаемо, зачем]
  ["PASS", "", "UNKNOWN", "ложный PASS при пустом ответе (сам дефект F-ROOM-1)"],
  ["PASS", "   ", "UNKNOWN", "пробелы — тоже пустой ответ"],
  ["PASS", null, "UNKNOWN", "ответ отсутствует целиком"],
  ["PASS", "29", "PASS", "положительный контроль: ответ есть"],
  ["FAIL", "", "FAIL", "провал остаётся провалом, пустой ответ его не отменяет"],
  ["UNKNOWN", "29", "UNKNOWN", "UNKNOWN не повышается до PASS"],
  ["garbage", "29", "UNKNOWN", "нераспознанный вердикт — UNKNOWN"],
];
let bad = 0;
for (const [reported, answer, want, why] of cases) {{
  const got = settleVerdict(reported, answer);
  const ok = got === want;
  if (!ok) bad++;
  console.log(`${{ok ? "ok  " : "FAIL"}} ${{JSON.stringify(reported)}} + ${{JSON.stringify(answer)}} -> ${{got}} (ждали ${{want}}): ${{why}}`);
}}
process.exit(bad ? 1 : 0);
"""
    code, out = run_node(script)
    return code == 0, out.strip().splitlines()


def check_journal() -> tuple[bool, list[str]]:
    """Чтение ответа из журнала: только из журнала ЭТОЙ задачи (F-ROOM-3)."""
    lines: list[str] = []
    ok_all = True
    with tempfile.TemporaryDirectory() as tmp:
        journal = Path(tmp) / "journal.bin"
        # Два прогона в одном журнале: ответ первой задачи не должен победить.
        first = "Первый ответ".encode("utf-8")
        second = "Второй ответ — 29 строк".encode("utf-8")
        journal.write_bytes(
            b"HSJ1\x01\x00\x00\x00" + b"run/end " + first + b"\x00"
            + b"run/end " + second + b"\x00"
        )
        script = f"""
import {{ answerFromJournal }} from {json.dumps(PLUGIN.as_uri())};
console.log(JSON.stringify(answerFromJournal({json.dumps(str(journal))})));
"""
        code, out = run_node(script)
        got = out.strip()
        # Node печатает кириллицу как есть, json.dumps по умолчанию экранирует —
        # сравниваем разобранные значения, а не строки JSON.
        try:
            value = json.loads(got)
        except json.JSONDecodeError:
            value = None
        want = second.decode("utf-8")
        ok = code == 0 and value == want
        ok_all &= ok
        lines.append(f"{'ok  ' if ok else 'FAIL'} два прогона: ждали {want!r}, получили {value!r}")

        # Нет журнала — пустая строка, а не падение.
        missing = Path(tmp) / "нет-такого.bin"
        script = f"""
import {{ answerFromJournal }} from {json.dumps(PLUGIN.as_uri())};
console.log(JSON.stringify(answerFromJournal({json.dumps(str(missing))})));
"""
        code, out = run_node(script)
        ok = code == 0 and out.strip() == '""'
        ok_all &= ok
        lines.append(f"{'ok  ' if ok else 'FAIL'} журнала нет: ждали пустую строку, получили {out.strip()}")

        # F-ROOM-3: журнал от ДРУГОЙ задачи не должен отдавать свой ответ.
        foreign = Path(tmp) / "чужой.bin"
        foreign.write_bytes(
            b"HSJ1\x01\x00\x00\x00"
            + b"run/start task: \xd0\xbf\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82\x00"
            + b"run/end " + "ответ на привет".encode("utf-8") + b"\x00"
        )
        script = f"""
import {{ answerFromJournal }} from {json.dumps(PLUGIN.as_uri())};
console.log(JSON.stringify(answerFromJournal(
  {json.dumps(str(foreign))}, "найди все текстовые файлы", 0)));
"""
        code, out = run_node(script)
        ok = code == 0 and out.strip() == '""'
        ok_all &= ok
        lines.append(
            f"{'ok  ' if ok else 'FAIL'} журнал чужой задачи: ждали пустую строку, получили {out.strip()}")

        # Положительный контроль: та же задача — ответ принимается.
        script = f"""
import {{ answerFromJournal }} from {json.dumps(PLUGIN.as_uri())};
console.log(JSON.stringify(answerFromJournal(
  {json.dumps(str(foreign))}, "привет", 0)));
"""
        code, out = run_node(script)
        try:
            value = json.loads(out.strip())
        except json.JSONDecodeError:
            value = None
        ok = code == 0 and value == "ответ на привет"
        ok_all &= ok
        lines.append(
            f"{'ok  ' if ok else 'FAIL'} журнал своей задачи: ждали 'ответ на привет', получили {value!r}")

        # Журнал старше прогона — не принимается, даже если задача совпала.
        old = Path(tmp) / "старый.bin"
        old.write_bytes(
            b"HSJ1\x01\x00\x00\x00"
            + b"run/start task: \xd0\xbf\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82\x00"
            + b"run/end " + "старый ответ".encode("utf-8") + b"\x00"
        )
        future = int(old.stat().st_mtime * 1000) + 60000
        script = f"""
import {{ answerFromJournal }} from {json.dumps(PLUGIN.as_uri())};
console.log(JSON.stringify(answerFromJournal(
  {json.dumps(str(old))}, "привет", {future})));
"""
        code, out = run_node(script)
        ok = code == 0 and out.strip() == '""'
        ok_all &= ok
        lines.append(
            f"{'ok  ' if ok else 'FAIL'} журнал старше прогона: ждали пустую строку, получили {out.strip()}")
    return ok_all, lines


def main(argv: list[str]) -> int:
    checks = [("вердикт", check_settle), ("журнал", check_journal)]
    failed = 0
    for title, fn in checks:
        ok, lines = fn()
        print(f"=== {title} ===")
        for line in lines:
            print(" ", line)
        if not ok:
            failed += 1
    print()
    if failed:
        print(f"[FAIL] проверок провалено: {failed} из {len(checks)}")
        return 1
    print(f"[ok] проверок пройдено: {len(checks)} из {len(checks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
