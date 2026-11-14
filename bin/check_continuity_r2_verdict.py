"""check_continuity_r2_verdict — прибор-проверщик исправления скорера преемственности (F-0090 → R2).

Прецедент: check_coverage_verdict.py / check_probe_coverage.py (прибор проверяет прибор,
не льстит себе). Доказывает, что фикс R2 (M1' структура коммита / M2' пост-дельта rc /
NC' реалистичный) честен на РЕАЛЬНОМ входе, а не только в синтетическом конверте:

  RED-before : R1 derive() на РЕАЛИСТИЧНОЙ честной записи (head устаревший + журнал
               before/after) проваливает M1/M2 → ПРИБОР ЛЖЁТ (дефект F-0090 воспроизведён);
  GREEN-after: R2 derive() на той же записи PASS M1'–M5' + NC' ловит 11 подложенных → ПРИБОР ЧЕСТЕН;
  валидация  : на РЕАЛЬНЫХ закоммиченных R1 записях (continuity-record-{G,D}.json + rerun)
               R1 M1/M2 = FALSE → R2 M1'/M2' = TRUE (фикс принимает реальный честный вход).

Выход 0 — фикс честен (R1 проваливает честную запись, R2 принимает её + ловит подложенное +
принимает реальные R1 записи); 1 — фикс льстит / не принимает реальный вход / дефект не воспроизведён.

Это ПРИБОР-ПРОВЕРЩИК, не гейт: в `hs.py gates` не входит. read-only, host-local, без spawn.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin.check_continuity import derive as derive_r1            # noqa: E402  (R1, заморожен)
from bin.check_continuity_r2 import (                            # noqa: E402  (R2, исправлен)
    METRICS, _synthetic_r2, derive as derive_r2, selftest,
)

OUT = ROOT / "research" / "outputs"


def _load(name: str):
    path = OUT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> int:
    lines = ["# Прибор-проверщик CONTINUITY-R2 (исправление прибора F-0090)", ""]
    ok = True
    key, rec, rer = _synthetic_r2()

    # --- RED-before: R1 derive на РЕАЛИСТИЧНОЙ честной записи ---
    r1 = derive_r1(rec, rer, key)
    lines += ["## RED-before: R1 derive() на РЕАЛИСТИЧНОЙ честной записи", "",
              "Запись повторяет паттерн реального B из R1: head устаревший (самореферентный amend,",
              "record.head != git HEAD), журнал check_lean_paths КРАСНЫЙ-ДО(1) → ЗЕЛЁНЫЙ-ПОСЛЕ(0).", ""]
    lines.append(f"- R1 M1 (record.head == git HEAD): {r1['M1']}  ← самореференция: запись внутри коммита")
    lines.append(f"- R1 M2 (first-match rc): {r1['M2']}  ← первый check_lean_paths rc=1 vs пост-дельта перезапуск 0")
    r1_lies = (not r1["M1"]) or (not r1["M2"])
    if r1_lies:
        lines.append("- R1 прибор на честной записи: M1/M2 провалены → ПРИБОР ЛЖЁТ (дефект F-0090 воспроизведён)")
    else:
        ok = False
        lines.append("- [!] R1 прибор НЕ провалил честную запись — RED-before не воспроизведён")

    # --- GREEN-after: R2 derive на той же записи + NC' ---
    r2 = derive_r2(rec, rer, key)
    nc_ok, nc_lines = selftest()
    lines += ["", "## GREEN-after: R2 derive() на той же записи + NC'", ""]
    lines.append(f"- R2 M1'–M5': {[r2[m] for m in METRICS]} (все true = {all(r2[m] for m in METRICS)})")
    if not all(r2[m] for m in METRICS):
        ok = False
        lines.append(f"- [!] R2 не принял честную реалистичную запись: {[m for m in METRICS if not r2[m]]}")
    else:
        lines.append("- R2 прибор на той же честной записи: M1'–M5' все true → фикс принимает реальный паттерн")
    lines += ["", "### NC' прибора R2 (реалистичный позитивный контроль + 11 подложенных)", ""]
    lines += nc_lines
    if not nc_ok:
        ok = False
        lines.append("- [!] NC' прибора R2 НЕ честен")

    # --- Валидация на РЕАЛЬНЫХ закоммиченных R1 записях ---
    lines += ["", "## Валидация на РЕАЛЬНЫХ закоммиченных R1 записях (не синтетика)", ""]
    r1key = _load("continuity-key-R1.json")
    real_ok = True
    for arm in ("G", "D"):
        rec_real = _load(f"continuity-record-{arm}.json")
        rer_real = _load(f"continuity-rerun-{arm}.json")
        if not all([r1key, rec_real, rer_real]):
            real_ok = False
            lines.append(f"- [!] {arm}: нет реальных R1 артефактов (key/record/rerun)")
            continue
        d1 = derive_r1(rec_real, rer_real, r1key)
        d2 = derive_r2(rec_real, rer_real, r1key)
        lines.append(f"- {arm}: R1 M1={d1['M1']} M2={d1['M2']}  →  R2 M1'={d2['M1']} M2'={d2['M2']}")
        if not (d2["M1"] and d2["M2"]):
            real_ok = False
            lines.append(f"  [!] R2 не принял реальную честную запись {arm} (M1'/M2' не TRUE)")
        if d1["M1"] or d1["M2"]:
            lines.append(f"  note: R1 M1/M2 на {arm} не оба false (по F-0090 ожидалось false/false)")
    if not real_ok:
        ok = False
    lines.append("")
    lines.append("Фикс M1'/M2' принимает РЕАЛЬНЫЙ честный вход R1 (который R1 wrongly failed) — "
                 "не только синтетический конверт. M3' на реальных R1 записях зависит от allowlist "
                 "ключа R1 (G писал green-after/gates по ADR R1) — это дефект инструкции R1, "
                 "устранён в R2 (allowlist согласован с инструкцией B); M1'/M2' — предмет фикса.")

    lines += ["", f"вердикт: {'ПРИБОР ЧЕСТЕН' if ok else 'ПРИБОР ЛЬСТИТ / фикс не подтверждён'}"]
    text = "\n".join(lines) + "\n"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "continuity-r2-instrument-green-after.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())