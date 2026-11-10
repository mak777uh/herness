#!/usr/bin/env python3
"""check-domain-table.py — таблица доменов подписи обязана сходиться со строками вызова (`H-0167`).

Почина. Каждый кодек объявляет `const DOMAIN` в `crates/vecdht-wire/src/messages.rs`, но вызовы
`sign_body`/`verify_body` называют домен своей строкой (`domain::WAL`, `b"vecdht/v8/match"`), а не
обращением к таблице. Таблица ничего не контролирует: расхождение между объявлением и вызовом не
ловится ничем, и на дереве `55bc71d` оно есть — `Kind::WalPullResponse` объявляет
`domain::WAL_PULL_RESP`, а шесть вызовов подписывают и проверяют в `domain::WAL`. Прибор не чинит
байты подписи (пересъём золотых векторов — отдельная карточка), он делает расхождение названным:
оно обязано стоять в `lab/domain-exceptions.tsv` с числом сайтов и причиной, иначе краснит.

Формы печати заморожены таблицей `lab/expectations/e0167.tsv`:
    DOMAIN_DECLS=<N>          сколько кодеков объявляют `const DOMAIN`
    DOMAIN_TABLE_READS=<N>    сколько вызовов берут домен из таблицы (`<Кодекс>::DOMAIN`)
    DOMAIN_SITES=<N>          сколько вызовов `sign_body`/`verify_body` прибор разобрал
    DOMAIN_UNRESOLVED=<N>     сколько вызовов разобрать не удалось (домен — переменная)
    DOMAIN_MISMATCH=<N>       число видов, где вызов расходится с таблицей
    DOMAIN_SITES_MISMATCH=<N> число таких вызовов
    DOMAIN_FINDINGS=<N>       непоименованные находки (0 — всё названо списком)
    DOMAIN_RC=<0|1>           код процесса
    DOMAIN_RASHOZHDENIE\t<вид>\t<объявлено>\t<употреблено>\t<число_сайтов>
    DOMAIN_NE_IZVESTNO\t<вид>\t<N>\t<класс>   строка списка названа, а в дереве её нет

Список исключений: `lab/domain-exceptions.tsv`, поля через табуляцию —
`<вид или класс><TAB><число сайтов><TAB><причина не короче 25 знаков>`. Пустая причина — находка.

Запуск: `python lab/check-domain-table.py` (боевой), `--selftest` (посадки), `--root <каталог>`.
"""

import argparse
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MESSAGES = os.path.join("crates", "vecdht-wire", "src", "messages.rs")
EXCEPTIONS = os.path.join("lab", "domain-exceptions.tsv")
UNRESOLVED_CLASS = "не_разобрано"
MIN_REASON = 25

CALL_RE = re.compile(r"\b(?:sign_body|verify_body)\s*\(([^)]*)\)", re.S)
DOMAIN_CONST_RE = re.compile(r"^\s*pub const ([A-Z_0-9]+): &\[u8\] = b\"([^\"]*)\";")
DECL_RE = re.compile(r"const KIND: Kind = Kind::(\w+);\s*\n\s*const DOMAIN: &'static \[u8\] = domain::([A-Z_0-9]+);")
KIND_RE = re.compile(r"Kind::(\w+)")
TABLE_READ_RE = re.compile(r"^([A-Z]\w*)::DOMAIN$")


def read(path):
    return io.open(path, encoding="utf-8").read()


def strip_comment(line):
    return re.sub(r"//.*$", "", line).rstrip()


def table(root):
    """(значение домена по имени, объявленный домен по виду) из `messages.rs`."""
    text = read(os.path.join(root, MESSAGES))
    values = {}
    for line in text.splitlines():
        m = DOMAIN_CONST_RE.match(line)
        if m:
            values[m.group(1)] = m.group(2)
    declared = dict(DECL_RE.findall(text))
    return values, declared


def strip_comments(text):
    """Комментарии вырезаны построчно, переводы строк сохранены: смещения остаются валидными."""
    return "\n".join(re.sub(r"//.*$", "", line) for line in text.splitlines())


def split_args(blob):
    """Разбор списка аргументов с учётом вложенных скобок и литералов байтовых строк."""
    args, depth, cur, in_str = [], 0, "", False
    i = 0
    while i < len(blob):
        ch = blob[i]
        if in_str:
            cur += ch
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            args.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    if cur.strip():
        args.append(cur.strip())
    return args


def call_sites(root):
    """Все вызовы подписи/проверки в `crates/**/*.rs`: (файл, строка, домен, вид).

    Позиции аргументов различаются: у `sign_body` домен первый, у `verify_body` первым идёт
    открытый ключ. Порядок задаёт таблица, а не догадка, иначе пропущенный аргумент превратился
    бы в «не разобрано» и расхождение ушло бы молча (тот же класс, что чинит карточка).
    """
    hits = []
    crates = os.path.join(root, "crates")
    for dirpath, _dirs, files in os.walk(crates):
        if os.sep + "target" + os.sep in dirpath:
            continue
        for fn in sorted(files):
            if not fn.endswith(".rs"):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            text = strip_comments(read(p))
            for m in re.finditer(r"\b(sign_body|verify_body)\s*\(", text):
                if text[:m.start()].rstrip().endswith("fn"):
                    continue  # объявление метода, а не вызов: аргументы там — параметры
                start = m.end()
                depth, i, in_str = 1, start, False
                while i < len(text) and depth:
                    ch = text[i]
                    if in_str:
                        if ch == '"':
                            in_str = False
                    elif ch == '"':
                        in_str = True
                    elif ch in "([{":
                        depth += 1
                    elif ch in ")]}":
                        depth -= 1
                    i += 1
                blob = text[start:i - 1]
                args = split_args(blob)
                di = 0 if m.group(1) == "sign_body" else 1
                dom = args[di] if len(args) > di else ""
                kind = None
                for a in args[di + 1:]:
                    km = KIND_RE.search(a)
                    if km:
                        kind = km.group(1)
                        break
                hits.append((rel, text[:m.start()].count("\n") + 1, dom, kind))
    return hits


def exceptions(root):
    rows = {}
    path = os.path.join(root, EXCEPTIONS)
    if not os.path.isfile(path):
        return rows
    for line in read(path).splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            rows.setdefault(line, (0, "строка без табуляции"))
            continue
        rows[parts[0]] = (int(parts[1]) if parts[1].strip().isdigit() else 0, parts[2])
    return rows


def scan(root):
    """(счётчики, строки находок). Счётчики — функция дерева, список исключений — функция реестра."""
    values, declared = table(root)
    rows = exceptions(root)
    sites = call_sites(root)
    mismatch = {}
    unresolved = 0
    table_reads = 0
    parsed = 0
    for rel, line, dom, kind in sites:
        if TABLE_READ_RE.match(dom):
            table_reads += 1
            continue
        expect = declared.get(kind) if kind else None
        got = None
        mm = re.fullmatch(r"(?:\w+::)*domain::([A-Z_0-9]+)", dom)
        if mm:
            got = mm.group(1)
        elif dom.startswith('b"'):
            lit = dom[2:].rstrip('"')
            got = next((n for n, v in values.items() if v == lit), None)
        if got is None or expect is None:
            unresolved += 1
            continue
        parsed += 1
        if got != expect:
            mismatch.setdefault(kind, {"got": got, "expect": expect, "sites": []})["sites"].append(
                f"{rel}:{line}")
    findings = []
    for kind in sorted(mismatch):
        n = len(mismatch[kind]["sites"])
        row = rows.get(f"Kind::{kind}")
        print("DOMAIN_RASHOZHDENIE\t%s\t%s\t%s\t%d" % (
            kind, mismatch[kind]["expect"], mismatch[kind]["got"], n))
        if row is None:
            findings.append(f"DOMAIN_NE_IZVESTNO\tKind::{kind}\t{n}\tдомен")
        elif row[0] != n:
            findings.append(f"DOMAIN_NE_IZVESTNO\tKind::{kind}\t{n}\tчисло_сайтов:{row[0]}")
        elif len(row[1].strip()) < MIN_REASON:
            findings.append(f"DOMAIN_NE_IZVESTNO\tKind::{kind}\t{n}\tпричина_короткая")
    for key in sorted(rows):
        if key.startswith("Kind::") and key.replace("Kind::", "") not in mismatch:
            findings.append(f"DOMAIN_STALE\t{key}\t{rows[key][0]}")
    n_unres = rows.get(UNRESOLVED_CLASS, (None, ""))[0]
    if n_unres is None and unresolved:
        findings.append(f"DOMAIN_NE_IZVESTNO\t{UNRESOLVED_CLASS}\t{unresolved}\tкласс")
    elif n_unres is not None and n_unres != unresolved:
        findings.append(f"DOMAIN_STALE\t{UNRESOLVED_CLASS}\t{unresolved}\tбыло:{n_unres}")
    counters = {
        "DOMAIN_DECLS": len(declared),
        "DOMAIN_TABLE_READS": table_reads,
        "DOMAIN_SITES": parsed,
        "DOMAIN_UNRESOLVED": unresolved,
        "DOMAIN_MISMATCH": len(mismatch),
        "DOMAIN_SITES_MISMATCH": sum(len(v["sites"]) for v in mismatch.values()),
        "DOMAIN_FINDINGS": len(findings),
    }
    return counters, findings


def plant_tree(dirpath, dom_walpull, extra_calls):
    """Мини-дерево: `messages.rs` с двумя кодеками и один файл с вызовами. Строки вызовов
    задаёт случай самопроверки, поэтому одна и та же посадка проверяет разбор и реестр."""
    os.makedirs(os.path.join(dirpath, "crates", "x", "src"), exist_ok=True)
    os.makedirs(os.path.join(dirpath, os.path.dirname(MESSAGES)), exist_ok=True)
    os.makedirs(os.path.join(dirpath, "lab"), exist_ok=True)
    io.open(os.path.join(dirpath, MESSAGES), "w", encoding="utf-8").write(
        "pub mod domain {\n"
        '    pub const ALPHA: &[u8] = b"vecdht/v8/alpha";\n'
        '    pub const BETA: &[u8] = b"vecdht/v8/beta";\n'
        "}\n"
        "impl Codec for Alpha {\n"
        "    const KIND: Kind = Kind::Alpha;\n"
        "    const DOMAIN: &'static [u8] = domain::ALPHA;\n"
        "}\n"
        "impl Codec for Beta {\n"
        "    const KIND: Kind = Kind::Beta;\n"
        "    const DOMAIN: &'static [u8] = domain::BETA;\n"
        "}\n")
    io.open(os.path.join(dirpath, "crates", "x", "src", "lib.rs"), "w",
            encoding="utf-8").write("\n".join(extra_calls) + "\n")
    if dom_walpull is not None:
        io.open(os.path.join(dirpath, EXCEPTIONS), "w", encoding="utf-8").write(dom_walpull + "\n")


def cmd_selftest(root):
    """Посадки на мини-дереве: расхождение без строки реестра краснит, названное — молчит,
    названное не тем числом сайтов — краснит, отжившая строка реестра — краснит."""
    import tempfile
    cases = [("расхождение без реестра", 1), ("расхождение названо", 1), ("названо не тем числом", 1),
             ("отжившая строка реестра", 1)]
    passed = 0
    call = ['    let sig = id.sign_body(domain::BETA, Kind::Alpha, &body);']
    tmp = tempfile.mkdtemp(prefix="check-domain-")
    plant_tree(os.path.join(tmp, "a"), None, call)
    _c, f = scan(os.path.join(tmp, "a"))
    if any(x.startswith("DOMAIN_NE_IZVESTNO\tKind::Alpha") for x in f):
        passed += 1
        print("САМОПРОВЕРКА: свежее расхождение без строки реестра краснит — ok")
    else:
        print("САМОПРОВЕРКА: свежее расхождение без строки реестра краснит — ПРОВАЛ")
    plant_tree(os.path.join(tmp, "b"), "Kind::Alpha\t1\tпосаженное расхождение домена для самопроверки",
               call)
    _c, f = scan(os.path.join(tmp, "b"))
    if not f:
        passed += 1
        print("САМОПРОВЕРКА: названное расхождение с верным числом сайтов молчит — ok")
    else:
        print("САМОПРОВЕРКА: названное расхождение с верным числом сайтов молчит — ПРОВАЛ")
    plant_tree(os.path.join(tmp, "c"), "Kind::Alpha\t2\tчисло сайтов завышено намеренно", call)
    _c, f = scan(os.path.join(tmp, "c"))
    if any("число_сайтов" in x for x in f):
        passed += 1
        print("САМОПРОВЕРКА: расхождение, названное не тем числом сайтов, краснит — ok")
    else:
        print("САМОПРОВЕРКА: расхождение, названное не тем числом сайтов, краснит — ПРОВАЛ")
    plant_tree(os.path.join(tmp, "d"),
               "Kind::Alpha\t1\tздесь всё верно\nKind::Gamma\t3\tстрока реестра о виде, которого нет",
               call)
    _c, f = scan(os.path.join(tmp, "d"))
    if any(x.startswith("DOMAIN_STALE\tKind::Gamma") for x in f):
        passed += 1
        print("САМОПРОВЕРКА: отжившая строка реестра краснит — ok")
    else:
        print("САМОПРОВЕРКА: отжившая строка реестра краснит — ПРОВАЛ")
    print(f"DOMAIN_SELFTEST={passed}/{len(cases)}")
    return 0 if passed == len(cases) else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--root", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    args = p.parse_args(argv)
    if args.selftest:
        return cmd_selftest(args.root)
    counters, findings = scan(args.root)
    for line in findings:
        print(line)
    for k in ("DOMAIN_DECLS", "DOMAIN_TABLE_READS", "DOMAIN_SITES", "DOMAIN_UNRESOLVED",
              "DOMAIN_MISMATCH", "DOMAIN_SITES_MISMATCH", "DOMAIN_FINDINGS"):
        print(f"{k}={counters[k]}")
    rc = 1 if findings else 0
    print(f"DOMAIN_RC={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
