"""Подсчёт H-0002: доля утверждений со ссылкой, точность ссылок, выдуманные числа."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\111\herness")
H2 = ROOT / "lab" / "h2"
SOURCES = ["P16-RESULTS.md", "P17-RESULTS.md", "P18-RESULTS.md", "SELF-WORK.md", "CYCLE.md"]

CITATION = re.compile(r"\[(" + "|".join(re.escape(name) for name in SOURCES) + r")\]")
MENTION = re.compile(r"(" + "|".join(re.escape(name[:-3]) for name in SOURCES) + r")")


def cited_in(sentence: str) -> list[str]:
    """Ссылка в любом виде: скобки или упоминание имени файла без расширения."""
    bracketed = CITATION.findall(sentence)
    mentioned = [name + ".md" for name in MENTION.findall(sentence)]
    return list(dict.fromkeys(bracketed + mentioned))
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if len(part.strip()) > 25]


def is_claim(sentence: str) -> bool:
    low = sentence.lower()
    return bool(NUMBER.search(sentence)) or any(word in low for word in
                                                ("дефект", "утвержд", "провер", "значит", "падает",
                                                 "совпал", "остал"))


def source_text(name: str) -> str:
    for path in (H2 / "A" / "run-1").iterdir():
        if path.name == name:
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def score(record: dict) -> dict:
    text = record.get("text", "")
    parts = sentences(text)
    claims = [sentence for sentence in parts if is_claim(sentence)]
    cited = [sentence for sentence in claims if cited_in(sentence)]
    citations = [name for sentence in parts for name in cited_in(sentence)]

    # precision: у каждой ссылки проверяем, есть ли число из того же предложения в файле
    correct, checked = 0, 0
    for sentence in cited:
        targets = set(cited_in(sentence))
        numbers = NUMBER.findall(sentence)
        if not numbers:
            continue
        checked += 1
        if any(any(number in source_text(name) for number in numbers) for name in targets):
            correct += 1

    # выдуманные числа: числа, которых нет ни в одном источнике
    all_sources = " ".join(source_text(name) for name in SOURCES)
    numbers = NUMBER.findall(text)
    invented = [number for number in numbers if number not in all_sources]

    return {"arm": record["arm"], "run": record["run"], "status": record["status"],
            "chars": len(text), "claims": len(claims), "cited": len(cited),
            "recall": round(len(cited) / len(claims), 2) if claims else 0.0,
            "citations": len(citations),
            "precision_checked": checked, "precision_ok": correct,
            "invented_numbers": len(set(invented)), "invented_sample": sorted(set(invented))[:6]}


def main() -> int:
    data = json.loads((H2 / "results.json").read_text(encoding="utf-8"))
    rows = [score(record) for record in data["records"]]
    (H2 / "scores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                                    encoding="utf-8")

    print(f"{'плечо':<6}{'прогон':<8}{'утв.':<6}{'со ссылкой':<12}{'recall':<8}{'ссылок':<8}"
          f"{'precision':<12}{'выдумано':<9}")
    for row in rows:
        precision = (f"{row['precision_ok']}/{row['precision_checked']}"
                     if row["precision_checked"] else "—")
        print(f"{row['arm']:<6}{row['run']:<8}{row['claims']:<6}{row['cited']:<12}"
              f"{row['recall']:<8}{row['citations']:<8}{precision:<12}{row['invented_numbers']:<9}")

    for arm in ("A", "B"):
        subset = [row for row in rows if row["arm"] == arm]
        if not subset:
            continue
        claims = sum(row["claims"] for row in subset)
        cited = sum(row["cited"] for row in subset)
        checked = sum(row["precision_checked"] for row in subset)
        correct = sum(row["precision_ok"] for row in subset)
        print(f"\n{arm}: утверждений {claims}, со ссылкой {cited} "
              f"(recall {cited / claims:.2f})" if claims else f"\n{arm}: утверждений нет",
              f"| precision {correct}/{checked}" if checked else "| precision не проверялась",
              f"| выдуманных чисел {sum(row['invented_numbers'] for row in subset)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
