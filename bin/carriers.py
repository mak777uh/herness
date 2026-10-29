"""carriers — установление того, чем держится утверждение.

Три вида носителя, и все три считаются отдельно (смешивать их — значит обманывать себя):

* **команда** — вывод исполняется и сверяется с ожиданием (`bin/verify_claims.py`);
* **свидетельство** — файл-артефакт прогона (существует и содержит то, на что ссылаются);
* **документ** — место, где формулировка написана дословно.

Печатается то, что есть. Ничего не «принимается».
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "CLAIMS.md"
STATUS_WORDS = re.compile(r"(?i)\b(готов|закрыт|измерен|проверен|работает)\w*")
ANCHOR = re.compile(r"\d")
RUNNABLE = re.compile(r"\b(python|pytest|git|bash|pwsh|node)\b")


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
                    "cmd": cells[3].strip("`"), "artifact": cells[4]})
    return out


def main() -> int:
    claims = rows()
    by_cmd: list[str] = []
    by_evidence: list[str] = []
    by_doc: list[str] = []
    no_anchor: list[str] = []

    for claim in claims:
        if RUNNABLE.search(claim["cmd"]):
            by_cmd.append(claim["id"])

        carrier = claim["artifact"]
        path = None
        if carrier and not carrier.startswith(("вывод",)):
            path = (ROOT / carrier).resolve()
        if path is not None and path.exists() and not path.is_dir():
            body = norm(path.read_text(encoding="utf-8", errors="replace"))
            if norm(claim["text"]) in body:
                by_doc.append(claim["id"])
            else:
                by_evidence.append(claim["id"])

        if STATUS_WORDS.search(claim["text"]) and not ANCHOR.search(claim["text"]):
            no_anchor.append(claim["id"])

    covered = set(by_cmd) | set(by_doc) | set(by_evidence)
    # снятое утверждение носителя не требует: его роль — помнить, что было отозвано
    covered |= {c["id"] for c in claims if c["type"].lower() in {"withdrawn", "снято"}}
    bare = [c["id"] for c in claims if c["id"] not in covered]

    print(f"утверждений: {len(claims)}")
    print(f"носитель-команда: {len(by_cmd)}")
    print(f"носитель-свидетельство (файл есть, формулировки нет): {len(by_evidence)}")
    print(f"носитель-документ (формулировка дословно): {len(by_doc)}")
    print(f"статусное слово без числа: {len(no_anchor)} {no_anchor}")
    print(f"без носителя вообще: {len(bare)} {bare}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
