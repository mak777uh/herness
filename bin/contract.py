"""contract — договор об отношениях для инструмента, в форме nomos.

Принцип: инструмент — не «функция», а договор между агентом и харнессом.
У договора есть атомы — позиции с носителем и противной стороной, как в nomos.

Договор можно менять: это не константа, а решение. Но у каждой правки есть версия и причина,
а прежняя версия остаётся в истории (append-only, как журнал).

    python bin/contract.py read              # показать договор
    python bin/contract.py --list            # какие есть
    python bin/contract.py read --check      # проверить структуру
    python bin/contract.py read --amend "причина"  # новая версия с причиной
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "lab" / "tools" / "contracts.json"
HISTORY = ROOT / "lab" / "tools" / "contracts-history.jsonl"

# Восемь позиций Хофельда, как в nomos.
RELATIONS = ("right", "duty", "privilege", "no_right",
             "power", "liability", "immunity", "disability")

CONTRACTS_DATA = {
    "read": {
        "work_id": "tool:read",
        "version": 1,
        "purpose": "дать агенту прочитать файл, не дав ему выйти за комнату и не утопив его в тексте",
        "atoms": [
            {"id": "a1", "relation": "right", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "read", "object": "file", "scope": "/mnt/**"},
             "conditions": ["path_inside_room"], "why": "без этого инструмент бесполезен"},
            {"id": "a2", "relation": "duty", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "cite", "object": "path:line"}, "negated": False,
             "why": "ответ без источника не считается результатом (наш гейт опоры)"},
            {"id": "a3", "relation": "duty", "bearer": "harness", "counterparty": "agent",
             "action": {"verb": "limit", "object": "output", "quantity": "8192B"}, "negated": False,
             "why": "контекст модели — бюджет, а не бесплатный ресурс"},
            {"id": "a4", "relation": "duty", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "write", "object": "file"}, "negated": True,
             "why": "чтение не должно менять то, что читает"},
            {"id": "a5", "relation": "duty", "bearer": "harness", "counterparty": "agent",
             "action": {"verb": "refuse", "object": "path_outside_room"}, "negated": False,
             "why": "замыкание объявлено — отказ обязан быть явным"},
        ],
        "escapes": [
            {"atom": "a6", "reason": "time_limit_not_enforced_by_kernel",
             "detail": "лимит 100 мс объявлен, но ядро его не проверяет; это уход, а не гарантия"},
        ],
        "verdicts": ["FULFILLED", "REFUSED", "VIOLATED"],
        "closure": {"fs": {"read": ["/mnt/**"], "write": []}, "net": [],
                    "time_ms": 100, "memory_mb": 4, "output_bytes": 8192},
    },
    "search": {
        "work_id": "tool:search",
        "version": 1,
        "purpose": "дать агенту найти нужное, не заставив его перечитывать всё",
        "atoms": [
            {"id": "a1", "relation": "right", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "search", "object": "files", "scope": "/mnt/**"},
             "conditions": ["path_inside_room"], "why": "поиск — основной способ найти ответ"},
            {"id": "a2", "relation": "duty", "bearer": "harness", "counterparty": "agent",
             "action": {"verb": "count", "object": "distinct_values"}, "negated": False,
             "why": "модель не умеет считать; число разных даёт харнесс"},
            {"id": "a3", "relation": "duty", "bearer": "harness", "counterparty": "agent",
             "action": {"verb": "show", "object": "context_around_match"}, "negated": False,
             "why": "совпадение без контекста бесполезно"},
            {"id": "a4", "relation": "duty", "bearer": "harness", "counterparty": "agent",
             "action": {"verb": "limit", "object": "output", "quantity": "16000B"}, "negated": False,
             "why": "контекст — бюджет"},
            {"id": "a5", "relation": "duty", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "write", "object": "file"}, "negated": True,
             "why": "поиск ничего не меняет"},
        ],
        "escapes": [
            {"atom": "a6", "reason": "case_insensitive_only",
             "detail": "регистр не важен; поиск по точной форме не поддерживается — это уход"},
        ],
        "verdicts": ["FULFILLED", "REFUSED", "VIOLATED"],
        "closure": {"fs": {"read": ["/mnt/**"], "write": []}, "net": [],
                    "time_ms": 2000, "memory_mb": 32, "output_bytes": 16000},
    },
    "list": {
        "work_id": "tool:list",
        "version": 1,
        "purpose": "дать агенту увидеть, что есть в каталоге, не утопив его в перечне",
        "atoms": [
            {"id": "a1", "relation": "right", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "list", "object": "directory", "scope": "/mnt/**"},
             "conditions": ["path_inside_room"], "why": "без этого агент не знает, что есть"},
            {"id": "a2", "relation": "duty", "bearer": "harness", "counterparty": "agent",
             "action": {"verb": "limit", "object": "entries", "quantity": "100"}, "negated": False,
             "why": "перечень на 93 файла модель не охватывает"},
            {"id": "a3", "relation": "duty", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "write", "object": "file"}, "negated": True,
             "why": "просмотр каталога ничего не меняет"},
        ],
        "escapes": [
            {"atom": "a4", "reason": "single_level_only",
             "detail": "рекурсии нет; дерево не показывается — это уход"},
        ],
        "verdicts": ["FULFILLED", "REFUSED", "VIOLATED"],
        "closure": {"fs": {"read": ["/mnt/**"], "write": []}, "net": [],
                    "time_ms": 200, "memory_mb": 8, "output_bytes": 8000},
    },
    "write": {
        "work_id": "tool:write",
        "version": 1,
        "purpose": "дать агенту записать результат, не дав испортить то, что вне его рабочего каталога",
        "atoms": [
            {"id": "a1", "relation": "right", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "write", "object": "file", "scope": "/mnt/work/**"},
             "conditions": ["path_inside_work"], "why": "без этого агент не может оставить результат"},
            {"id": "a2", "relation": "duty", "bearer": "harness", "counterparty": "agent",
             "action": {"verb": "refuse", "object": "path_outside_work"}, "negated": False,
             "why": "запись вне рабочего каталога — отказ, а не молчание"},
            {"id": "a3", "relation": "duty", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "overwrite", "object": "outside_scope"}, "negated": True,
             "why": "перезапись чужих файлов — нарушение договора"},
        ],
        "escapes": [
            {"atom": "a4", "reason": "no_edit_only_overwrite",
             "detail": "правки нет, только перезапись целиком — это уход, а не удобство"},
        ],
        "verdicts": ["FULFILLED", "REFUSED", "VIOLATED"],
        "closure": {"fs": {"read": ["/mnt/**"], "write": ["/mnt/work/**"]}, "net": [],
                    "time_ms": 200, "memory_mb": 8, "output_bytes": 500},
    },
    "seal": {
        "work_id": "tool:seal",
        "version": 1,
        "purpose": "дать агенту зафиксировать содержимое отпечатком, чтобы правка была видна",
        "atoms": [
            {"id": "a1", "relation": "right", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "seal", "object": "file", "scope": "/mnt/work/**"},
             "conditions": ["path_inside_work"], "why": "отпечаток — способ зафиксировать"},
            {"id": "a2", "relation": "duty", "bearer": "harness", "counterparty": "agent",
             "action": {"verb": "return", "object": "digest"}, "negated": False,
             "why": "отпечаток без значения бесполезен"},
            {"id": "a3", "relation": "duty", "bearer": "harness", "counterparty": "agent",
             "action": {"verb": "seal", "object": "content_after_marker"}, "negated": True,
             "why": "правка после маркера не должна менять отпечаток — иначе он бесполезен"},
        ],
        "escapes": [
            {"atom": "a4", "reason": "marker_based_scope",
             "detail": "отпечаток считается до маркера «## Seal»; это договорённость, а не свойство"},
        ],
        "verdicts": ["FULFILLED", "REFUSED", "VIOLATED"],
        "closure": {"fs": {"read": ["/mnt/**"], "write": ["/mnt/work/**"]}, "net": [],
                    "time_ms": 200, "memory_mb": 8, "output_bytes": 500},
    },
    "netprobe": {
        "work_id": "tool:netprobe",
        "version": 1,
        "purpose": "дать агенту проверить, доступен ли адрес, не дав выйти в сеть",
        "atoms": [
            {"id": "a1", "relation": "right", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "probe", "object": "address", "scope": "10.0.2.2:8790"},
             "conditions": ["address_in_allowlist"], "why": "единственный разрешённый адрес — мост"},
            {"id": "a2", "relation": "duty", "bearer": "harness", "counterparty": "agent",
             "action": {"verb": "refuse", "object": "address_outside_allowlist"}, "negated": False,
             "why": "сеть за мостом — отказ, а не попытка"},
            {"id": "a3", "relation": "duty", "bearer": "agent", "counterparty": "harness",
             "action": {"verb": "download", "object": "content"}, "negated": True,
             "why": "проверка доступности не должна тянуть содержимое"},
        ],
        "escapes": [
            {"atom": "a4", "reason": "reachability_only",
             "detail": "проверяется только доступность; содержимое не читается — это уход"},
        ],
        "verdicts": ["FULFILLED", "REFUSED", "VIOLATED"],
        "closure": {"fs": {"read": [], "write": []}, "net": ["10.0.2.2:8790"],
                    "time_ms": 3000, "memory_mb": 4, "output_bytes": 500},
    },
}


def load() -> dict:
    if CONTRACTS.exists():
        return json.loads(CONTRACTS.read_text(encoding="utf-8"))
    return CONTRACTS_DATA


def problems(contract: dict) -> list[str]:
    """Проверка договора: у каждого атома есть позиция, стороны, действие и причина."""
    out = []
    atoms = contract.get("atoms") or []
    if not atoms:
        out.append("нет ни одного атома")
    seen = set()
    for atom in atoms:
        ident = atom.get("id")
        if not ident:
            out.append("атом без id")
            continue
        if ident in seen:
            out.append(f"повтор атома {ident}")
        seen.add(ident)
        if atom.get("relation") not in RELATIONS:
            out.append(f"{ident}: позиция {atom.get('relation')} не из восьми")
        for field in ("bearer", "counterparty", "action", "why"):
            if not atom.get(field):
                out.append(f"{ident}: нет поля {field}")
        action = atom.get("action") or {}
        if not action.get("verb"):
            out.append(f"{ident}: у действия нет глагола")
    for escape in contract.get("escapes") or []:
        if escape.get("atom") in seen:
            out.append(f"уход указывает на объявленный атом {escape.get('atom')} — это не уход")
        if not escape.get("reason"):
            out.append("уход без причины")
    if not contract.get("closure"):
        out.append("нет замыкания")
    if not contract.get("version"):
        out.append("нет версии договора")
    return out


def show(name: str) -> int:
    contract = load().get(name)
    if not contract:
        print(f"нет договора для {name}", file=sys.stderr)
        return 2
    print(f"# Договор: {contract['work_id']} (версия {contract['version']})")
    print(f"\n{contract['purpose']}\n")
    print("| атом | позиция | носитель | против | действие | почему |")
    print("|---|---|---|---|---|---|")
    for atom in contract["atoms"]:
        action = atom["action"]
        negated = " (запрет)" if atom.get("negated") else ""
        verb = f"{action['verb']} {action.get('object', '')}{negated}".strip()
        print(f"| {atom['id']} | {atom['relation']} | {atom['bearer']} | {atom['counterparty']} | {verb} | {atom['why']} |")
    if contract.get("escapes"):
        print("\n## Уходы (объявленные не-гарантии)")
        for escape in contract["escapes"]:
            print(f"- {escape['atom']}: {escape['reason']} — {escape.get('detail', '')}")
    print(f"\n## Вердикты: {', '.join(contract['verdicts'])}")
    return 0


def amend(name: str, reason: str) -> int:
    """Новая версия договора с причиной; прежняя остаётся в истории."""
    data = load()
    contract = data.get(name)
    if not contract:
        print(f"нет договора для {name}", file=sys.stderr)
        return 2
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"tool": name, "version": contract["version"],
                                 "reason": reason, "at": stamp,
                                 "contract": contract}, ensure_ascii=False) + "\n")
    contract["version"] = int(contract["version"]) + 1
    contract["amended_at"] = stamp
    contract["amend_reason"] = reason
    CONTRACTS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{name}: версия {contract['version'] - 1} → {contract['version']}; причина: {reason}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="договор об отношениях инструмента")
    parser.add_argument("tool", nargs="?")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--build", action="store_true", help="записать договоры в файл")
    parser.add_argument("--amend", metavar="ПРИЧИНА", help="новая версия с причиной")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.build:
        CONTRACTS.parent.mkdir(parents=True, exist_ok=True)
        CONTRACTS.write_text(json.dumps(CONTRACTS_DATA, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"записано: {CONTRACTS.relative_to(ROOT)}; договоров {len(CONTRACTS_DATA)}")
        return 0
    if args.list:
        print("\n".join(load()))
        return 0
    if not args.tool:
        print("нужно имя инструмента", file=sys.stderr)
        return 2
    if args.amend:
        return amend(args.tool, args.amend)
    if args.check:
        found = problems(load()[args.tool])
        if found:
            print("ПРОБЛЕМЫ:")
            for item in found:
                print("  -", item)
            return 1
        print(f"[ok] договор {args.tool} согласован")
        return 0
    return show(args.tool)


if __name__ == "__main__":
    sys.exit(main())
