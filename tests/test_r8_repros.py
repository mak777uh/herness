"""R8-репро: дефекты, из-за которых `head` был бы зелёным по ложной причине.

Каждая проверка — утверждение о ФИКСИРОВАННОМ состоянии. На коде до R8 они падают;
после патчей этапов 2-8 проходят. Это не доказательство безопасности: проверка видит
исходники и артефакты, а не поведение изолированной комнаты. Поведение доказывают
Rust-тесты и HEAD-SLICE-R1.

    python tests/test_r8_repros.py            # отчёт, rc=1 при любом провале
    python tests/test_r8_repros.py --list     # только имена проверок
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "core-rs" / "src" / "loopmod.rs"
POLICY_JSON = ROOT / "lab" / "tools" / "policy.json"
SCHEMA = ROOT / "lab" / "tools" / "tool-card-v1.schema.json"
DRAFT = ROOT / "lab" / "tools" / "drafts" / "head-v1.draft.json"
CODES = ROOT / "lab" / "refusal-codes.json"

CHECKS: list[tuple[str, callable]] = []


def check(name: str):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def source() -> str:
    return LOOP.read_text(encoding="utf-8")


def body(src: str, name: str) -> str:
    """Тело одной top-level функции: от `fn name` до следующей top-level строки."""
    start = src.find(f"fn {name}(")
    if start < 0:
        start = src.find(f"fn {name}<")
    assert start >= 0, f"в loopmod.rs нет функции {name}"
    rest = src[start + 1:]
    stops = [m.start() for m in re.finditer(r"(?m)^(?:pub )?(?:fn|const|impl|enum|struct|#\[cfg)", rest)]
    end = start + 1 + stops[0] if stops else len(src)
    return src[start:end]


def code_only(text: str) -> str:
    """Убрать строчные комментарии: проверка не должна зеленеть от слова в комментарии."""
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def policy_rules() -> list[dict]:
    return list(json.loads(POLICY_JSON.read_text(encoding="utf-8"))["rules"])


@check("REPRO-POLICY-COUNT")
def policy_count() -> str:
    src = source()
    assert 'include_str!("../../lab/tools/policy.json")' in src, \
        "Rust не встраивает policy.json через include_str!"
    assert "pub const POLICY" not in src, "в Rust осталась ручная копия POLICY — два источника"
    assert not re.search(r'Rule\s*\{\s*tool:\s*"', src), \
        "в Rust есть литеральные Rule { tool: \"...\" } — ручная копия политики"
    rules = policy_rules()
    assert len(rules) == 23, f"policy.json: {len(rules)} правил, ждали 23"
    ids = [rule.get("id") for rule in rules]
    assert len(set(ids)) == len(ids), "в policy.json повторяются id"
    return "один источник, 23 правила"


@check("REPRO-POLICY-BANG")
def policy_bang() -> str:
    fn = body(source(), "resource_matches")
    assert "strip_prefix('!')" in fn or 'strip_prefix("!")' in fn, \
        "resource_matches не понимает `!` (дополнение): file:!/mnt/** и net:!10.0.2.2:8790 не работают"
    return "`!` реализован"


@check("REPRO-RESOLVE-READ")
def resolve_read() -> str:
    fn = body(source(), "resolve_in")
    assert 'policy_allows("read", "read"' not in fn, \
        "resolve_in всегда проверяет read/read: write/list/search проверяют чужое действие"
    return "resolve_in не решает за инструмент"


@check("REPRO-WRITE-TRUNC")
def write_trunc() -> str:
    fn = code_only(body(source(), "write_beneath"))
    assert "O_TRUNC" not in fn, "write_beneath использует O_TRUNC: существующий файл перезаписывается"
    assert "O_EXCL" in fn, "write_beneath не использует O_EXCL: create-new не обеспечен"
    return "create-new через O_EXCL"


@check("REPRO-WRITE-XDEV")
def write_xdev() -> str:
    fn = code_only(body(source(), "write_beneath"))
    assert "RESOLVE_NO_XDEV" in fn, "write_beneath не запрещает переход на другую ФС"
    assert "RESOLVE_NO_MAGICLINKS" in fn, "write_beneath не запрещает magic links"
    return "NO_XDEV и NO_MAGICLINKS стоят"


@check("REPRO-WRITE-POLICY-BEFORE-OPEN")
def write_policy_norm() -> str:
    fn = body(source(), "tool_write_in")
    assert "resource_of" in fn and "normalize" in fn, \
        "tool_write_in проверяет policy над ненормализованным путём: work/../work2 проходит"
    return "policy видит нормализованный путь"


@check("REPRO-READ-WHOLE")
def read_whole() -> str:
    fn = body(source(), "tool_read_in")
    assert "read_to_string" not in fn, "tool_read_in читает весь файл до лимита выдачи"
    return "read не читает файл целиком"


@check("REPRO-READ-CAP")
def read_cap() -> str:
    fn = body(source(), "tool_read_in")
    assert "READ_OUTPUT" in fn or "8192" in fn or "8 * 1024" in fn, \
        "у read нет отдельного потолка выдачи 8192 B: одна строка может переполнить ответ"
    return "потолок выдачи отдельный"


@check("REPRO-SEARCH-SILENT")
def search_silent() -> str:
    fn = body(source(), "tool_search_in")
    assert "else { continue }" not in fn, \
        "search молча пропускает ошибки metadata/read: «0 найдено» врёт"
    assert "read_to_string" not in fn or "S12_ENCODING" in fn, \
        "ошибка UTF-8 не имеет явного кода"
    return "ошибки search явные"


@check("REPRO-SEARCH-UNICODE")
def search_unicode() -> str:
    fn = body(source(), "tool_search_in")
    assert "lower_line.find" not in fn, \
        "позиция в lowercased строке используется как байтовый индекс исходной: паника на İ€"
    assert "line[position..]" not in fn, "срез исходной строки по позиции lowercased"
    return "поиск не режет строку по чужой позиции"


@check("REPRO-LIST-FLATTEN")
def list_flatten() -> str:
    fn = body(source(), "tool_list_in")
    assert "entries.flatten()" not in fn, "list молча глотает ошибки read_dir"
    assert "metadata().ok()" not in fn, "list показывает битую запись как файл размера 0"
    return "ошибки list явные"


@check("REPRO-LIST-DOUBLE")
def list_double() -> str:
    fn = body(source(), "tool_list_in")
    assert fn.count("resolve_in") <= 1, "list делает resolve_in дважды: TOCTOU между проверкой и чтением"
    return "один resolve"


@check("REPRO-SELF-EXEC")
def self_exec() -> str:
    for name in ("tool_seal", "tool_netprobe"):
        fn = body(source(), name)
        assert "current_exe" not in fn, f"{name} запускает сам себя через current_exe"
    return "self-exec убран"


@check("REPRO-ADMISSION")
def admission() -> str:
    fn = code_only(body(source(), "run_tool_g"))
    assert "registry" in fn or "admission" in fn, \
        "run_tool_g не проверяет admission/derived active: любой инструмент запускается по имени"
    assert "S13_TOOL_INACTIVE" in fn, "нет отказа S13_TOOL_INACTIVE"
    return "authority проверяется"


@check("REPRO-HEAD-CARD")
def head_card() -> str:
    legacy = json.loads((ROOT / "lab" / "tools" / "cards" / "head.json").read_text(encoding="utf-8"))
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    assert legacy["id"] != draft["id"], \
        f"две карточки с одним id={draft['id']!r} в разных форматах: неизвестно, какая закон"
    return "id карточек различаются"


@check("REPRO-REFUSAL-V3")
def refusal_v3() -> str:
    data = json.loads(CODES.read_text(encoding="utf-8"))
    assert data["version"] == 3, f"словарь отказов версии {data['version']}, ждали 3"
    codes = {item["code"] for item in data["codes"]}
    for code in ("S10_NOT_FOUND", "S11_NOT_REGULAR", "S12_ENCODING",
                 "S13_TOOL_INACTIVE", "S14_ALREADY_EXISTS"):
        assert code in codes, f"нет кода {code}"
    return "v3, 28 кодов"


@check("REPRO-SCHEMA-ENUM")
def schema_enum() -> str:
    data = json.loads(CODES.read_text(encoding="utf-8"))
    codes = {item["code"] for item in data["codes"]}
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    enum = set(schema["properties"]["refusals"]["items"]["enum"])
    assert enum == codes, f"enum схемы и словарь расходятся: {sorted(enum ^ codes)}"
    return "enum == словарь"


@check("REPRO-DRAFT-ENUM")
def draft_enum() -> str:
    data = json.loads(CODES.read_text(encoding="utf-8"))
    codes = {item["code"] for item in data["codes"]}
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    unknown = sorted(set(draft["refusals"]) - codes)
    assert not unknown, f"карточка ссылается на коды вне словаря: {unknown}"
    return "карточка использует только словарь"


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for name, _ in CHECKS:
            print(name)
        return 0
    failed = 0
    for name, fn in CHECKS:
        try:
            detail = fn()
            print(f"[ok]   {name}: {detail}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[FAIL] {name}: {exc}")
    print(f"\nпроверок: {len(CHECKS)}, провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
