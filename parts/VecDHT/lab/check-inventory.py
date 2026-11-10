#!/usr/bin/env python3
"""check-inventory.py — снимок `lab/INVENTORY.md` обязан равняться пересчёту (карточка `H-0167`).

Почина. `lab/inventory.py` умеет пересчитывать счётчики и записывать таблицу, но до этого прибора
никто не сверял напечатанный снимок со свежим пересчётом: на дереве `55bc71d` снимок утверждал
`hypotheses=158`, а пересчёт давал 159, и контур был зелёный. Прибор судит по наличию совпадения,
а не по отсутствию проверки: он перебирает строки с обеих сторон, поэтому лишняя строка в снимке
и пропущенная в снимке краснят одинаково.

Формы печати заморожены таблицей `lab/expectations/e0167.tsv`:
    INVENTORY_SNAPSHOT=1     файл снимка разбирается
    INVENTORY_RECOMPUTE=1    пересчёт удался
    INVENTORY_KEYS=<N>       сколько счётчиков даёт пересчёт
    INVENTORY_ROWS=<N>       сколько строк в снимке
    INVENTORY_DIFF=<N>       число расхождений (0 означает, что снимок равен пересчёту)
    INVENTORY_RC=<0|1>       код, который вернёт процесс
    INVENTORY_RASHOZHDENIE<TAB><имя><TAB><снимок><TAB><пересчёт><TAB><класс>

Классы расхождения: `ЧИСЛО` (значения разошлись), `НЕ_НАЗВАН` (пересчёт дал счётчик, которого в
снимке нет), `ЛИШНИЙ` (в снимке есть строка, которой нет в пересчёте), `СНИМОК_НЕ_РАЗОБРАН`,
`ПЕРЕСЧЁТ_УПАЛ`.

Запуск: `python lab/check-inventory.py` (боевой), `--selftest` (посадки), `--root <каталог>`.
"""

import argparse
import io
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROW_RE = re.compile(r"^\|\s*`([a-z0-9_\-]+)`\s*\|\s*(\d+)\s*\|")
DATE_RE = re.compile(r"^Дата этого среза:\s*(\d{4}-\d{2}-\d{2})", re.M)


def read(path):
    return io.open(path, encoding="utf-8").read()


def parse_snapshot(path):
    """Таблица снимка -> ({имя счётчика: напечатанное число}, дата среза или None)."""
    if not os.path.isfile(path):
        return None, None
    text = read(path)
    rows = {}
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if m:
            rows[m.group(1)] = int(m.group(2))
    if not rows:
        return None, None
    dm = DATE_RE.search(text)
    return rows, (dm.group(1) if dm else None)


def recompute(root):
    """Свежий пересчёт тех же счётчиков — той же программой, которая пишет снимок."""
    script = os.path.join(root, "lab", "inventory.py")
    try:
        p = subprocess.run([sys.executable, script], capture_output=True, text=True,
                           cwd=root, timeout=900)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    out = {}
    for line in p.stdout.splitlines():
        if re.match(r"^[a-z0-9_\-]+=\d+$", line.strip()):
            k, v = line.strip().split("=")
            out[k] = int(v)
    return out or None


def judge(snap, rec):
    """Строки расхождений между снимком и пересчётом; пустой список — снимок равен пересчёту."""
    if snap is None:
        return ["INVENTORY_RASHOZHDENIE\tфайл\tнет\t-\tСНИМОК_НЕ_РАЗОБРАН"]
    if rec is None:
        return ["INVENTORY_RASHOZHDENIE\tпересчёт\t-\tнет\tПЕРЕСЧЁТ_УПАЛ"]
    diffs = []
    for k in sorted(rec):
        if k not in snap:
            diffs.append(f"INVENTORY_RASHOZHDENIE\t{k}\tнет\t{rec[k]}\tНЕ_НАЗВАН")
        elif snap[k] != rec[k]:
            diffs.append(f"INVENTORY_RASHOZHDENIE\t{k}\t{snap[k]}\t{rec[k]}\tЧИСЛО")
    for k in sorted(snap):
        if k not in rec:
            diffs.append(f"INVENTORY_RASHOZHDENIE\t{k}\t{snap[k]}\tнет\tЛИШНИЙ")
    return diffs


def live_state(root):
    snap, _date = parse_snapshot(os.path.join(root, "lab", "INVENTORY.md"))
    return snap, recompute(root)


def cmd_selftest(root):
    """Три посадки: подменённое число, вычеркнутая строка, лишняя строка. Каждая обязана краснить."""
    snap, rec = live_state(root)
    if rec is None:
        print("INVENTORY_SELFTEST=0/3")
        print("  ПЕРЕСЧЁТ_УПАЛ: самопроверка не на чём считать")
        return 1
    path = os.path.join(root, "lab", "INVENTORY.md")
    text = read(path)
    first = sorted(rec)[0]
    cases = [("подменённое число", 1), ("вычеркнутая строка", 1), ("лишняя строка", 1)]
    passed = 0

    # посадка 1: у первой строки таблицы число сдвинуто на единицу
    mutated = re.sub(r"(^\|\s*`" + re.escape(first) + r"`\s*\|\s*)(\d+)(\s*\|)",
                     lambda m: m.group(1) + str(int(m.group(2)) + 1) + m.group(3),
                     text, count=1, flags=re.M)
    d = judge(parse_snapshot_from_text(mutated), rec)
    if any(x.endswith("\tЧИСЛО") for x in d):
        passed += 1
        print(f"САМОПРОВЕРКА {first}: подменённое число краснит — ok")
    else:
        print(f"САМОПРОВЕРКА {first}: подменённое число краснит — ПРОВАЛ")

    # посадка 2: строка счётчика вычеркнута целиком
    dropped = "\n".join(l for l in text.splitlines()
                        if not re.match(r"^\|\s*`" + re.escape(first) + r"`\s*\|", l))
    d = judge(parse_snapshot_from_text(dropped), rec)
    if any(x.endswith("\tНЕ_НАЗВАН") for x in d):
        passed += 1
        print("САМОПРОВЕРКА: вычеркнутая строка краснит — ok")
    else:
        print("САМОПРОВЕРКА: вычеркнутая строка краснит — ПРОВАЛ")

    # посадка 3: в таблицу вставлена строка, которой пересчёт не даёт
    extra = re.sub(r"(^\|\s*`" + re.escape(first) + r"`\s*\|\s*\d+\s*\|.*$)",
                   lambda m: m.group(1) + "\n| `storonniy_schetchik` | 7 | нет такой команды |",
                   text, count=1, flags=re.M)
    d = judge(parse_snapshot_from_text(extra), rec)
    if any("ЛИШНИЙ" in x for x in d):
        passed += 1
        print("САМОПРОВЕРКА: лишняя строка краснит — ok")
    else:
        print("САМОПРОВЕРКА: лишняя строка краснит — ПРОВАЛ")

    print(f"INVENTORY_SELFTEST={passed}/{len(cases)}")
    return 0 if passed == len(cases) else 1


def parse_snapshot_from_text(text):
    rows = {}
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if m:
            rows[m.group(1)] = int(m.group(2))
    return rows or None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--root", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    args = p.parse_args(argv)
    if args.selftest:
        return cmd_selftest(args.root)
    snap, rec = live_state(args.root)
    diffs = judge(snap, rec)
    print(f"INVENTORY_SNAPSHOT={1 if snap is not None else 0}")
    print(f"INVENTORY_RECOMPUTE={1 if rec is not None else 0}")
    print(f"INVENTORY_KEYS={len(rec) if rec else 0}")
    print(f"INVENTORY_ROWS={len(snap) if snap else 0}")
    for line in diffs:
        print(line)
    print(f"INVENTORY_DIFF={len(diffs)}")
    rc = 1 if diffs else 0
    print(f"INVENTORY_RC={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
