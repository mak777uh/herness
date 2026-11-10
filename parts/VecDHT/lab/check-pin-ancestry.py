#!/usr/bin/env python3
"""check-pin-ancestry.py — страж предковости пина (ADR-0078).

Предмет. Носитель (`lab/eNNNN-run.sh`), который вычисляет пин и печатает PRE-факты, обязан проверить,
что пин является предком HEAD, и обязан отказаться снимать PRE-числа, если это не так. Причина появления
— `E-0167`, закрытый вердиктом `refutes`: замороженное `PRE_FIX_BAD=10` было снято с суррогатного
коммита, собранного `commit-tree` до пре-регистрации, а на настоящем пине тот же прибор печатает 9.
Порядок замера стал правилом, а не памятью автора карточки.

Класс (определение живёт здесь, а не только в карточке): файл `lab/eNNNN-run.sh`, в котором есть строка
присваивания пина (`PIN=`/`pin=` в начале строки) И который печатает хоть один `PRE_FIX_`-факт.
Соответствие: в тексте носителя есть форма `PIN_IS_ANCESTOR`. Отдельная ветка — носитель, принимающий
внешний пин (`PIN=${PIN_OVERRIDE:-...}`): для него гейт обязателен без исключений, потому что именно
так и строится суррогатное дерево.

Освобождение — только строкой `lab/pin-ancestry-exceptions.tsv` (носитель, дата, причина не короче
25 знаков, обязанная называть карточку круга): исторические носители закрытых кругов не переписываются,
но их несоответствие становится видимым фактом дерева, а не молчанием прибора (доктрина `ADR-0077`).
"""

import os
import re
import subprocess
import sys

CARRIER_RE = re.compile(r"^lab/e\d{4}-run\.sh$")
PIN_ASSIGN_RE = re.compile(r"^[ \t]*(PIN|pin)=")
PRE_FACT_RE = re.compile(r"PRE_FIX_")
GATE_RE = re.compile(r"PIN_IS_ANCESTOR")
OVERRIDE_RE = re.compile(r"^[ \t]*(PIN|pin)=\$\{PIN_OVERRIDE", re.M)
EXCEPTION_PATH = "lab/pin-ancestry-exceptions.tsv"
MIN_REASON = 25


def repo_root(argv_root=None):
    if argv_root:
        return os.path.abspath(argv_root)
    env = os.environ.get("VEC_DHT_ROOT")
    if env:
        return os.path.abspath(env)
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=False)
    return out.stdout.strip() or os.getcwd()


def carrier_files(root):
    lab = os.path.join(root, "lab")
    if not os.path.isdir(lab):
        return []
    return sorted("lab/" + n for n in os.listdir(lab) if CARRIER_RE.match("lab/" + n))


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def in_scope(text):
    return (any(PIN_ASSIGN_RE.match(line) for line in text.splitlines())
            and bool(PRE_FACT_RE.search(text)))


def load_registry(root):
    """{носитель: причина} плюс находки о самих строках реестра."""
    text = read(os.path.join(root, EXCEPTION_PATH))
    if text is None:
        return {}, [f"{EXCEPTION_PATH}: реестра освобождений нет — нечем называть исторические носители"], 0
    rows, broken = {}, []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = [c.strip() for c in line.split("\t")]
        if len(cols) < 3 or not CARRIER_RE.match(cols[0]):
            broken.append(f"{EXCEPTION_PATH}: строка «{line[:48]}» без тройки носитель-дата-причина")
            continue
        carrier, date, reason = cols[0], cols[1], cols[2]
        if len(reason) < MIN_REASON:
            broken.append(f"{carrier}: освобождение в {len(reason)} знаков — это не причина")
            continue
        if "H-" not in reason and "E-" not in reason:
            broken.append(f"{carrier}: причина освобождения не называет карточку круга")
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            broken.append(f"{carrier}: дата освобождения «{date}» не в форме ГГГГ-ММ-ДД")
            continue
        rows[carrier] = reason
    return rows, broken, len(rows)


def scan(root):
    reg, findings, registry_rows = load_registry(root)
    findings = list(findings)
    scoped = gated = exempt_used = 0
    scope_set = set()
    for rel in carrier_files(root):
        text = read(os.path.join(root, rel))
        if text is None or not in_scope(text):
            continue
        scoped += 1
        scope_set.add(rel)
        if GATE_RE.search(text):
            gated += 1
            if OVERRIDE_RE.search(text) and not re.search(r"merge-base --is-ancestor", text):
                findings.append(f"{rel}: принимает внешний пин и печатает гейт, но не зовёт "
                                f"`merge-base --is-ancestor` — форма без механизма")
            continue
        if OVERRIDE_RE.search(text):
            findings.append(f"{rel}: принимает внешний пин и не проверяет предковость — PRE-число "
                            f"можно снять с дерева, которого нет в истории")
            continue
        if rel in reg:
            exempt_used += 1
            continue
        findings.append(f"{rel}: снимает PRE-факты без гейта предковости и не назван строкой "
                        f"{EXCEPTION_PATH}")
    for rel in sorted(reg):
        if rel not in scope_set:
            findings.append(f"{rel}: строка реестра освобождений, а носителя нет в классе — "
                            f"освобождение устарело")
    return {"scoped": scoped, "gated": gated, "exempt": exempt_used,
            "registry": registry_rows, "findings": findings}


CASES = [
    # (а) в классе, без гейта, не назван реестром -> обязан краснеть
    ("unregistered_nongated",
     {"lab/e0999-run.sh": "PIN=deadbeef\nemit PRE_FIX_THING \"$(x)\"\n"},
     "# реестр освобождений\n", True),
    # (б) в классе, с гейтом -> обязан быть чистым
    ("gated_clean",
     {"lab/e0999-run.sh": "PIN=deadbeef\ngit merge-base --is-ancestor \"$PIN\" HEAD\n"
                          "emit PIN_IS_ANCESTOR 1\nemit PRE_FIX_THING \"$(x)\"\n"},
     "# реестр освобождений\n", False),
    # (в) принимает внешний пин и без гейта -> краснеет даже с названной строкой реестра
    ("override_nongated",
     {"lab/e0999-run.sh": "PIN=${PIN_OVERRIDE:-$(git log --format=%H --reverse -- x.md | head -1)}\n"
                          "emit PRE_FIX_THING \"$(x)\"\n"},
     "lab/e0999-run.sh\t2026-11-01\tE-0167: исторический носитель, дерево его замера не переписывается\n",
     True),
    # (г) строка реестра про носителя, которого нет в классе -> краснеет (освобождение устарело)
    ("orphan_registry_row",
     {"lab/e0999-run.sh": "PIN=deadbeef\nemit PIN_IS_ANCESTOR 1\nemit PRE_FIX_THING \"$(x)\"\n"},
     "lab/e0888-run.sh\t2026-11-01\tE-0888: освобождение носителя, которого больше нет в классе\n",
     True),
]


def selftest():
    import tempfile
    total = len(CASES)
    detected = 0
    for name, files, registry, want_bad in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "lab"), exist_ok=True)
            for rel, body in files.items():
                with open(os.path.join(tmp, rel), "w", encoding="utf-8") as fh:
                    fh.write(body)
            with open(os.path.join(tmp, "lab", "pin-ancestry-exceptions.tsv"), "w", encoding="utf-8") as fh:
                fh.write(registry)
            got = scan(tmp)
            bad = bool(got["findings"])
            if bad == want_bad:
                detected += 1
            else:
                print(f"ПРОТИВ\t{name}\tожидалось_находок={'>=1' if want_bad else '0'}"
                      f"\tполучено={len(got['findings'])}")
    print(f"PIN_ANCESTRY_SELFTEST total={total} planted={detected} passed={detected}")
    return 0 if detected == total else 1


def main(argv):
    args = argv[1:]
    if "--selftest" in args:
        return selftest()
    root = args[args.index("--root") + 1] if "--root" in args else None
    got = scan(repo_root(root))
    print(f"PIN_ANCESTRY findings={len(got['findings'])} class={got['scoped']} "
          f"gated={got['gated']} exempt={got['exempt']} registry={got['registry']}")
    for f in got["findings"]:
        print(f"PIN_ANCESTRY_FINDING\t{f}")
    return 1 if got["findings"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
