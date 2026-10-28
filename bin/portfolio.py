#!/usr/bin/env python3
"""portfolio — матрица зрелости портфеля по кэшу справочника и метаданным GitHub.

Не делает сетевых вызовов: читает research/repos-api.json (снят отдельно) и refs-cache/.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "refs-cache"
API = ROOT / "research" / "repos-api.json"
OUT = ROOT / "research" / "PORTFOLIO.md"

CONVENTIONS = {
    "agents": "AGENTS.md",
    "claims": "CLAIMS.md",
    "not_claimed": "NOT-CLAIMED.md",
    "interop": "interop/README.md",
}


def main() -> int:
    api = {r["name"]: r for r in json.loads(API.read_text(encoding="utf-8"))}
    index = {}
    idx_path = CACHE / "index.json"
    if idx_path.exists():
        index = json.loads(idx_path.read_text(encoding="utf-8"))

    rows = []
    for name, meta in api.items():
        docs = index.get(name, {})
        flags = {k: (v in docs) for k, v in CONVENTIONS.items()}
        score = sum(flags.values())
        readme = docs.get("README.md", {}).get("bytes", 0)
        rows.append({
            "name": name,
            "pushed": str(meta.get("pushed_at", ""))[:10],
            "lang": meta.get("language") or "—",
            "kb": round((meta.get("size") or 0) / 1024, 1),  # GitHub отдаёт KB → показываем МБ
            "archived": bool(meta.get("archived")),
            "score": score,
            "readme_kb": round(readme / 1024, 1),
            "stub": readme < 500 and (meta.get("size") or 0) < 1024,
            **flags,
        })

    rows.sort(key=lambda r: (-r["score"], r["pushed"]), reverse=False)

    total = len(rows)
    have = {k: sum(1 for r in rows if r[k]) for k in CONVENTIONS}
    stubs = [r["name"] for r in rows if r["stub"]]
    lines = [
        "# PORTFOLIO — матрица зрелости",
        "",
        f"Репозиториев: {total}. Источник: `research/repos-api.json` + кэш справочника.",
        "",
        "## Покрытие дисциплины",
        "",
        "| документ | есть в | доля |",
        "|---|---|---|",
    ]
    for key, doc in CONVENTIONS.items():
        lines.append(f"| `{doc}` | {have[key]} | {round(100 * have[key] / total)}% |")

    lines += [
        "",
        "## Репозитории",
        "",
        "| репозиторий | pushed | язык | размер, МБ | AGENTS | CLAIMS | NOT-CLAIMED | interop | балл |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        mark = lambda flag: "✓" if r[flag] else "·"  # noqa: E731
        lines.append(
            f"| `{r['name']}` | {r['pushed']} | {r['lang']} | {r['kb']} | "
            f"{mark('agents')} | {mark('claims')} | {mark('not_claimed')} | {mark('interop')} | {r['score']}/4 |"
        )

    lines += [
        "",
        "## Наблюдения",
        "",
        f"- Полный набор дисциплины (4/4) — у {sum(1 for r in rows if r['score'] == 4)} репозиториев.",
        f"- Без `AGENTS.md` — у {total - have['agents']}.",
        f"- Без `NOT-CLAIMED.md` — у {total - have['not_claimed']}.",
        f"- Заглушки (README < 0,5 КБ) — {len(stubs)}: {', '.join(stubs) if stubs else 'нет'}.",
        "",
        "## Что это не доказывает",
        "",
        "- Наличие файла ≠ соблюдение правила: это матрица присутствия, а не поведения.",
        "- Кэш мог не содержать документ по причине 404 при синхронизации, а не его отсутствия.",
        "- Размер репозитория в API — без учёта git-истории.",
    ]

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"записано: {OUT}")
    print(f"покрытие: {have}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
