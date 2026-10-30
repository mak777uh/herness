"""Разбор собранных отчётов: темы, тяга, оценка, релевантность нам."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\111\herness")
REPORTS = ROOT / "research" / "hn-reports"

THEMES = {
    "проверяемость/свидетельства": ["verify", "verify", "evidence", "audit", "proof", "reproduc", "hash-seal", "provenance"],
    "агентская безопасность": ["firewall", "guard", "secrets", "sandbox", "permission", "block"],
    "память/контекст": ["memory", "context", "recall", "remember"],
    "MCP/инструменты": ["mcp", "tool", "plugin", "sdk"],
    "наблюдаемость": ["observability", "trace", "telemetry", "monitor", "log"],
    "данные/парсинг": ["scrape", "crawl", "parse", "extract", "dataset"],
    "финансы/крипто": ["payment", "wallet", "crypto", "usdc", "defi", "kyc"],
    "агенты-оркестрация": ["agent", "workflow", "orchestr", "autonomous"],
}

TRACTION = [
    (r"([\d.,]+\s*[Kk]?\+?)\s*(?:combined\s+)?(?:lifetime\s+)?downloads", "downloads"),
    (r"([\d.,]+\s*[Kk]?\+?)\s*(?:github\s+)?stars", "stars"),
    (r"([\d.,]+\s*[Kk]?\+?)\s*(?:merged\s+)?pull requests", "PRs"),
    (r"([\d.,]+\s*[Kk]?\+?)\s*(?:monthly\s+)?(?:active\s+)?users", "users"),
    (r"\$\s*([\d.,]+\s*[KkMm]?)\s*(?:MRR|ARR|monthly|in revenue)", "revenue"),
]


def body_of(text: str) -> str:
    head, _, tail = text.partition("\n\n")
    return tail or text


def main() -> int:
    rows = []
    for path in sorted(REPORTS.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        title = (re.search(r"^TITLE: (.*)$", text, re.M) or [None, path.stem])[1]
        score_match = re.search(r"^SCORE: ([\d.]+|None)$", text, re.M)
        score = float(score_match.group(1)) if score_match and score_match.group(1) != "None" else None
        body = body_of(text).lower()
        themes = [name for name, words in THEMES.items() if sum(body.count(word) for word in words) >= 3]
        traction = {}
        for pattern, label in TRACTION:
            match = re.search(pattern, body)
            if match:
                traction[label] = match.group(1).strip()
        rows.append({"file": path.name, "title": title[:120], "score": score,
                     "themes": themes, "traction": traction, "size": len(text)})

    scored = [row for row in rows if row["score"] is not None]
    print(f"файлов: {len(rows)} | с оценкой: {len(scored)}")
    print("\n=== все с оценкой (по убыванию) ===")
    for row in sorted(scored, key=lambda r: -(r["score"] or 0)):
        traction = ", ".join(f"{key} {value}" for key, value in row["traction"].items()) or "нет чисел"
        print(f"{row['score']:>6} | {row['title'][:70]:<70} | {traction[:40]}")

    print("\n=== темы ===")
    counter = Counter(theme for row in rows for theme in row["themes"])
    for theme, count in counter.most_common():
        print(f"  {theme:<28} {count}")

    print("\n=== без оценки (не отчёты или без балла) ===")
    for row in rows:
        if row["score"] is None:
            print("  ", row["title"][:90])

    out = ROOT / "research" / "hn-reports-index.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nзаписано:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
