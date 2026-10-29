"""carriers — установление, а не решение.

Для каждого утверждения в CLAIMS.md проверяем два факта, которые можно установить командой:

1. Носитель: формулировка встречается в файле-носителе дословно (с точностью до пробелов).
2. Якорь: если в формулировке есть статусное слово (готов / закрыт / измерен / проверен), в ней же
   обязано быть число или процент.

Ничего не «принимается»: печатается то, что есть.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "CLAIMS.md"
STATUS_WORDS = re.compile(r"(?i)\b(готов|закрыт|измерен|проверен|работает)\w*")
ANCHOR = re.compile(r"\d")


def norm(text: str) -> str:
    return " ".join(text.split())


def rows() -> list[dict]:
    out = []
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| C-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        out.append({"id": cells[0], "text": cells[1], "type": cells[2],
                    "cmd": cells[3].strip("`"), "artifact": cells[4], "date": cells[5]})
    return out


def main() -> int:
    claims = rows()
    no_file = []
    not_found = []
    no_anchor = []
    ok = []

    for claim in claims:
        carrier = claim["artifact"]
        path = (ROOT / carrier).resolve() if carrier and not carrier.startswith(("вывод", "runs/")) else None
        has_anchor = bool(STATUS_WORDS.search(claim["text"]) and ANCHOR.search(claim["text"]))

        if STATUS_WORDS.search(claim["text"]) and not ANCHOR.search(claim["text"]):
            no_anchor.append(claim["id"])

        if path is None or not path.exists():
            no_file.append(claim["id"])
            continue
        body = norm(path.read_text(encoding="utf-8", errors="replace"))
        if norm(claim["text"]) in body:
            ok.append(claim["id"])
        else:
            not_found.append(claim["id"])

    print(f"утверждений: {len(claims)}")
    print(f"дословно в носителе: {len(ok)}")
    print(f"носитель есть, формулировки нет: {len(not_found)} {not_found}")
    print(f"носителя-файла нет: {len(no_file)} {no_file}")
    print(f"статусное слово без числа: {len(no_anchor)} {no_anchor}")

    runnable = re.compile(r"\b(python|pytest|git|bash|pwsh|node)\b")
    with_cmd = [c["id"] for c in claims if runnable.search(c["cmd"])]
    no_carrier = [c["id"] for c in claims
                  if c["id"] not in with_cmd and c["id"] not in ok]
    print(f"с исполняемой командой: {len(with_cmd)}")
    print(f"без носителя вообще (ни файла, ни команды): {len(no_carrier)} {no_carrier}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

