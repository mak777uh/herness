"""new_tool.py — генератор кандидатов одного шаблона `file_read_stream`.

Что делает: берёт спецификацию (`herness-tool-spec-v1`) и пишет в
`lab/candidates/file_read_stream/<spec-id>/` пять артефактов:

    spec.json              точные байты спецификации
    source.rs              кандидатная реализация (pure, без I/O и зависимостей)
    tests.rs               сгенерированные проверки по кейсам спецификации
    card.json              кандидатная карточка `tool-card-v1`
    policy.fragment.json   фрагмент политики, НЕ влитый в активную policy
    generation.json        digest'ы спецификации, шаблона и артефактов

Границы (Stage 9): генератор не пишет в `lab/tools/policy.json`, реестр,
admission и не выдаёт `active`. Кандидат — не инструмент: его нельзя запускать
через `run_tool_g`, пока владелец не подпишет admission по A01/Q15.

    python bin/new_tool.py --spec lab/pilot/specs/authored/frs-a01.json
    python bin/new_tool.py --all lab/pilot/specs --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "lab" / "candidates"
OUT_ROOT = CANDIDATES / "file_read_stream"
POLICY = ROOT / "lab" / "tools" / "policy.json"
ROOM = ROOT / "lab" / "tools" / "room-profile-v0.json"
SCHEMA = ROOT / "lab" / "tools" / "tool-card-v1.schema.json"
LAWSET = ROOT / "docs" / "CONSTITUTION-v0-2026-11-16.md"
CODES = ROOT / "lab" / "refusal-codes.json"

TEMPLATE = "file_read_stream"
TEMPLATE_VERSION = 1
GENERATOR = "herness-new-tool-v1"
SPEC_SCHEMA = "herness-tool-spec-v1"
CHUNK = 4096
OUTPUT_BYTES = 8192
MIN_LINES, MAX_LINES = 1, 200
MIN_MAX_BYTES, MAX_MAX_BYTES = 1, 65536
SAFE_ID = re.compile(r"^[a-z][a-z0-9-]{0,47}$")

SPEC_FIELDS = {
    "schema", "id", "template", "title", "line_count", "max_bytes_read",
    "path", "data_class", "cases",
}

# ------------------------------------------------------------------ reference


def reference_stream(data: bytes, line_count: int, max_bytes_read: int) -> dict:
    """S02-эталон для ожиданий спецификаций и проверки их согласованности.

    Это не доказательство корректности Rust-кандидата: эталон и шаблон написаны
    раздельно, а совпадение проверяется на зафиксированных кейсах пилота.
    """
    def err(code: str) -> dict:
        return {"outcome": "error", "code": code}

    if not (MIN_LINES <= line_count <= MAX_LINES):
        return err("S1_SCHEMA")
    if not (MIN_MAX_BYTES <= max_bytes_read <= MAX_MAX_BYTES):
        return err("S1_SCHEMA")

    lines: list[bytes] = []
    bytes_read = 0
    bytes_received = 0
    pending = bytearray()
    index = 0
    stop = "eof"
    eof = False
    stopped = False

    while not stopped:
        if len(lines) >= line_count:
            stop = "line_cap"
            break
        if bytes_received >= max_bytes_read:
            stop = "byte_cap"
            break
        want = min(CHUNK, max_bytes_read - bytes_received)
        take = min(want, len(data) - index)
        if take == 0:
            eof = True
            break
        bytes_received += take
        pending.extend(data[index:index + take])
        index += take
        while True:
            position = pending.find(b"\n")
            if position < 0:
                break
            line = bytes(pending[:position + 1])
            del pending[:position + 1]
            if bytes_read + len(line) > OUTPUT_BYTES:
                stop = "output_cap"
                stopped = True
                break
            try:
                content = line[:-1].decode("utf-8")
            except UnicodeDecodeError:
                return err("S12_ENCODING")
            lines.append(content.encode("utf-8"))
            bytes_read += len(line)
            if len(lines) >= line_count:
                stop = "line_cap"
                stopped = True
                break
        if stopped:
            break
        if bytes_received >= max_bytes_read:
            if not lines and pending:
                return err("K4_RESOURCE_LIMIT")
            stop = "byte_cap"
            break

    if eof and pending and len(lines) < line_count:
        line = bytes(pending)
        pending.clear()
        if bytes_read + len(line) > OUTPUT_BYTES:
            stop = "output_cap"
        else:
            try:
                content = line[:-1].decode("utf-8") if line.endswith(b"\n") else line.decode("utf-8")
            except UnicodeDecodeError:
                return err("S12_ENCODING")
            lines.append(content.encode("utf-8"))
            bytes_read += len(line)

    return {
        "outcome": "ok",
        "lines_hex": [line.hex() for line in lines],
        "bytes_read": bytes_read,
        "bytes_received": bytes_received,
        "truncated": stop != "eof",
        "stop_reason": stop,
    }


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


# ------------------------------------------------------------------ validation


def load_spec(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: спецификация не объект")
    return data


def validate_spec(spec: dict) -> list[str]:
    problems: list[str] = []
    missing = sorted(SPEC_FIELDS - set(spec))
    if missing:
        problems.append(f"нет полей: {', '.join(missing)}")
    extra = sorted(set(spec) - SPEC_FIELDS)
    if extra:
        problems.append(f"лишние поля: {', '.join(extra)}")
    if spec.get("schema") != SPEC_SCHEMA:
        problems.append(f"schema={spec.get('schema')!r}, ждали {SPEC_SCHEMA}")
    if spec.get("template") != TEMPLATE:
        problems.append(f"template={spec.get('template')!r}, ждали {TEMPLATE}")
    if not SAFE_ID.match(str(spec.get("id") or "")):
        problems.append(f"id={spec.get('id')!r} не соответствует {SAFE_ID.pattern}")
    if not isinstance(spec.get("title"), str) or not spec.get("title"):
        problems.append("title пуст")
    line_count = spec.get("line_count")
    max_bytes = spec.get("max_bytes_read")
    if not isinstance(line_count, int) or isinstance(line_count, bool) or not (
            MIN_LINES <= line_count <= MAX_LINES):
        problems.append(f"line_count={line_count!r} вне [{MIN_LINES}, {MAX_LINES}]")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not (
            MIN_MAX_BYTES <= max_bytes <= MAX_MAX_BYTES):
        problems.append(f"max_bytes_read={max_bytes!r} вне [{MIN_MAX_BYTES}, {MAX_MAX_BYTES}]")
    path = spec.get("path")
    if not isinstance(path, list) or len(path) < 2 or path[0] != "fixtures":
        problems.append("path должен начинаться с fixtures и содержать файл")
    else:
        for segment in path:
            if not isinstance(segment, str) or segment in {"", ".", ".."} or "/" in segment \
                    or "\\" in segment or "\x00" in segment:
                problems.append(f"небезопасный сегмент пути: {segment!r}")
    if spec.get("data_class") != "model_visible":
        problems.append(f"data_class={spec.get('data_class')!r}; первый срез — только model_visible")
    cases = spec.get("cases")
    if not isinstance(cases, list) or not cases:
        problems.append("cases пуст")
        return problems
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            problems.append(f"case[{index}] не объект")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not re.match(r"^[a-z0-9][a-z0-9-]{0,31}$", case_id):
            problems.append(f"case[{index}] id небезопасен: {case_id!r}")
        if case_id in seen:
            problems.append(f"повтор case id {case_id}")
        seen.add(case_id)
        line_count = case.get("line_count", spec.get("line_count"))
        max_bytes = case.get("max_bytes_read", spec.get("max_bytes_read"))
        try:
            data = bytes.fromhex(case.get("input_hex", ""))
        except ValueError:
            problems.append(f"case {case_id}: input_hex не hex")
            continue
        expected = reference_stream(data, line_count, max_bytes)
        declared = case.get("expect")
        if not isinstance(declared, dict):
            problems.append(f"case {case_id}: нет expect")
            continue
        if declared != expected:
            problems.append(
                f"case {case_id}: expect не совпадает с S02-эталоном\n"
                f"  declared={json.dumps(declared, ensure_ascii=False, sort_keys=True)}\n"
                f"  reference={json.dumps(expected, ensure_ascii=False, sort_keys=True)}"
            )
    return problems


# ------------------------------------------------------------------ rendering


SOURCE_TEMPLATE = r'''// Кандидат, сгенерированный herness new_tool.py (__GENERATOR__).
// Шаблон: __TEMPLATE__@__VERSION__. Это НЕ допущенный инструмент:
// admission отсутствует, registry.active его не содержит.
//
// Чистая функция над байтами: без файлов, сети, процессов и системного времени.
// S02: CHUNK=4096; CR сохраняется; строка выдаётся только целиком; EOF только
// при исчерпании входа; truncated=false только при доказанном EOF; output_cap —
// остановка, не отказ; max_bytes_read ограничивает принятые байты.

pub const CHUNK: usize = 4096;
pub const OUTPUT_BYTES: usize = 8192;
pub const MIN_LINES: usize = 1;
pub const MAX_LINES: usize = 200;
pub const MIN_MAX_BYTES: usize = 1;
pub const MAX_MAX_BYTES: usize = 65536;
pub const SPEC_ID: &str = "__SPEC_ID__";
pub const DEFAULT_LINE_COUNT: usize = __DEFAULT_LINE_COUNT__;
pub const DEFAULT_MAX_BYTES_READ: usize = __DEFAULT_MAX_BYTES_READ__;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Request {
    pub line_count: usize,
    pub max_bytes_read: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Outcome {
    pub lines: Vec<String>,
    pub bytes_read: usize,
    pub bytes_received: usize,
    pub truncated: bool,
    pub stop_reason: StopReason,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StopReason {
    Eof,
    LineCap,
    ByteCap,
    OutputCap,
}

impl StopReason {
    pub fn as_str(&self) -> &'static str {
        match self {
            StopReason::Eof => "eof",
            StopReason::LineCap => "line_cap",
            StopReason::ByteCap => "byte_cap",
            StopReason::OutputCap => "output_cap",
        }
    }
}

fn schema_error(reason: impl AsRef<str>) -> String {
    format!("S1_SCHEMA: {}", reason.as_ref())
}

fn encoding_error(reason: impl AsRef<str>) -> String {
    format!("S12_ENCODING: {}", reason.as_ref())
}

fn limit_error(reason: impl AsRef<str>) -> String {
    format!("K4_RESOURCE_LIMIT: {}", reason.as_ref())
}

fn check_schema(request: &Request) -> Result<(), String> {
    if !(MIN_LINES..=MAX_LINES).contains(&request.line_count) {
        return Err(schema_error(format!(
            "line_count={} вне [{MIN_LINES}, {MAX_LINES}]",
            request.line_count
        )));
    }
    if !(MIN_MAX_BYTES..=MAX_MAX_BYTES).contains(&request.max_bytes_read) {
        return Err(schema_error(format!(
            "max_bytes_read={} вне [{MIN_MAX_BYTES}, {MAX_MAX_BYTES}]",
            request.max_bytes_read
        )));
    }
    Ok(())
}

fn line_exceeds_output(bytes_read: usize, line: &[u8]) -> bool {
    bytes_read
        .checked_add(line.len())
        .is_none_or(|total| total > OUTPUT_BYTES)
}

fn emit_line(
    line_bytes: &[u8],
    lines: &mut Vec<String>,
    bytes_read: &mut usize,
) -> Result<(), String> {
    let content = line_bytes.strip_suffix(b"\n").unwrap_or(line_bytes);
    let text = std::str::from_utf8(content)
        .map_err(|error| encoding_error(format!("выданная строка не UTF-8: {error}")))?;
    lines.push(text.to_string());
    *bytes_read += line_bytes.len();
    Ok(())
}

pub fn stream(input: &[u8], request: &Request) -> Result<Outcome, String> {
    check_schema(request)?;

    let mut lines: Vec<String> = Vec::new();
    let mut bytes_read = 0usize;
    let mut bytes_received = 0usize;
    let mut pending: Vec<u8> = Vec::new();
    let mut index = 0usize;
    let mut stop_reason = StopReason::Eof;
    let mut eof = false;

    'outer: loop {
        if lines.len() >= request.line_count {
            stop_reason = StopReason::LineCap;
            break;
        }
        if bytes_received >= request.max_bytes_read {
            stop_reason = StopReason::ByteCap;
            break;
        }
        let want = CHUNK.min(request.max_bytes_read - bytes_received);
        let available = input.len() - index;
        let take = want.min(available);
        if take == 0 {
            eof = true;
            break;
        }
        bytes_received += take;
        pending.extend_from_slice(&input[index..index + take]);
        index += take;

        while let Some(position) = pending.iter().position(|byte| *byte == b'\n') {
            let line: Vec<u8> = pending.drain(..=position).collect();
            if line_exceeds_output(bytes_read, &line) {
                stop_reason = StopReason::OutputCap;
                break 'outer;
            }
            emit_line(&line, &mut lines, &mut bytes_read)?;
            if lines.len() >= request.line_count {
                stop_reason = StopReason::LineCap;
                break 'outer;
            }
        }

        if bytes_received >= request.max_bytes_read {
            if lines.is_empty() && !pending.is_empty() {
                return Err(limit_error(format!(
                    "max_bytes_read={} меньше первой строки",
                    request.max_bytes_read
                )));
            }
            stop_reason = StopReason::ByteCap;
            break;
        }
    }

    if eof && !pending.is_empty() && lines.len() < request.line_count {
        let line = std::mem::take(&mut pending);
        if line_exceeds_output(bytes_read, &line) {
            stop_reason = StopReason::OutputCap;
        } else {
            emit_line(&line, &mut lines, &mut bytes_read)?;
        }
    }

    let truncated = stop_reason != StopReason::Eof;
    Ok(Outcome {
        lines,
        bytes_read,
        bytes_received,
        truncated,
        stop_reason,
    })
}
'''


def render_source(spec: dict) -> str:
    return (SOURCE_TEMPLATE
            .replace("__GENERATOR__", GENERATOR)
            .replace("__TEMPLATE__", TEMPLATE)
            .replace("__VERSION__", str(TEMPLATE_VERSION))
            .replace("__SPEC_ID__", spec["id"])
            .replace("__DEFAULT_LINE_COUNT__", str(spec["line_count"]))
            .replace("__DEFAULT_MAX_BYTES_READ__", str(spec["max_bytes_read"])))


def rust_bytes(hex_text: str) -> str:
    raw = bytes.fromhex(hex_text)
    return "&[" + ", ".join(f"0x{byte:02x}" for byte in raw) + "]"


def render_case_function(spec: dict, case: dict, index: int) -> str:
    case_id = case["id"]
    line_count = case.get("line_count", spec["line_count"])
    max_bytes = case.get("max_bytes_read", spec["max_bytes_read"])
    expected = case["expect"]
    lines = [
        f"fn case_{index}(failures: &mut usize) -> usize {{",
        f"    let input: &[u8] = {rust_bytes(case.get('input_hex', ''))};",
        "    let request = Request {",
        f"        line_count: {line_count},",
        f"        max_bytes_read: {max_bytes},",
        "    };",
        "    match stream(input, &request) {",
        "        Ok(output) => {",
    ]
    if expected["outcome"] != "ok":
        lines += [
            "            println!(\"[FAIL] {case}: ожидался отказ " + expected["code"] + ", получен ok\");",
            "            *failures += 1;",
        ]
    else:
        expected_lines = expected["lines_hex"]
        lines += [
            f"            let expected_lines: Vec<Vec<u8>> = vec![{', '.join('vec![' + ', '.join(f'0x{byte:02x}' for byte in bytes.fromhex(h)) + ']' for h in expected_lines)}];",
            "            let actual_lines: Vec<Vec<u8>> = output.lines.iter()"
            ".map(|line| line.as_bytes().to_vec()).collect();",
            "            if actual_lines != expected_lines {",
            "                println!(\"[FAIL] {case}: lines={} expected={}\", actual_lines.len(), expected_lines.len());",
            "                *failures += 1;",
            "            }",
            f"            if output.bytes_read != {expected['bytes_read']} {{",
            "                println!(\"[FAIL] {case}: bytes_read={} expected={}\", output.bytes_read, "
            f"{expected['bytes_read']});",
            "                *failures += 1;",
            "            }",
            f"            if output.bytes_received != {expected['bytes_received']} {{",
            "                println!(\"[FAIL] {case}: bytes_received={} expected={}\", output.bytes_received, "
            f"{expected['bytes_received']});",
            "                *failures += 1;",
            "            }",
            f"            if output.truncated != {str(expected['truncated']).lower()} {{",
            "                println!(\"[FAIL] {case}: truncated={} expected={}\", output.truncated, "
            f"{str(expected['truncated']).lower()});",
            "                *failures += 1;",
            "            }",
            f"            if output.stop_reason.as_str() != \"{expected['stop_reason']}\" {{",
            "                println!(\"[FAIL] {case}: stop_reason={} expected={}\", "
            f"output.stop_reason.as_str(), \"{expected['stop_reason']}\");",
            "                *failures += 1;",
            "            }",
        ]
    lines += [
        "            1",
        "        }",
        "        Err(code) => {",
    ]
    if expected["outcome"] == "ok":
        lines += [
            "            println!(\"[FAIL] {case}: получен отказ {code}, ожидался ok\");",
            "            *failures += 1;",
        ]
    else:
        lines += [
            f"            if !code.starts_with(\"{expected['code']}:\") {{",
            "                println!(\"[FAIL] {case}: code={} expected="
            f"{expected['code']}\", code);",
            "                *failures += 1;",
            "            }",
        ]
    lines += ["            1", "        }", "    }", "}"]
    return "\n".join(lines).replace("{case}", case_id)


def render_run_function(spec: dict, offset: int) -> tuple[str, str]:
    ident = spec["id"].replace("-", "_")
    body = [f"fn run_{ident}(failures: &mut usize) -> usize {{", "    0"]
    for index in range(len(spec["cases"])):
        body.append(f"    + case_{offset + index}(failures)")
    body.append("}")
    return f"run_{ident}", "\n".join(body)


def render_harness(specs: list[dict]) -> str:
    """Один исполняемый harness: include!(source.rs) + кейсы + main."""
    lines = ['include!("source.rs");', ""]
    total_cases = 0
    offset = 0
    for spec in specs:
        for index, case in enumerate(spec["cases"]):
            lines.append(render_case_function(spec, case, offset + index))
            lines.append("")
        run_name, run_fn = render_run_function(spec, offset)
        offset += len(spec["cases"])
        total_cases += len(spec["cases"])
        lines.append(run_fn)
        lines.append("")
    lines.append("fn main() {")
    lines.append("    let mut failures = 0usize;")
    lines.append("    let mut cases = 0usize;")
    for spec in specs:
        run_name = "run_" + spec["id"].replace("-", "_")
        lines.append("    {")
        lines.append("        let before = failures;")
        lines.append(f"        cases += {run_name}(&mut failures);")
        lines.append(
            f"        println!(\"spec={spec['id']} cases={len(spec['cases'])} failures={{}}\", "
            "failures - before);"
        )
        lines.append("    }")
    lines.append(f"    if cases != {total_cases} {{")
    lines.append(f"        println!(\"[FAIL] cases={{}} expected={total_cases}\", cases);")
    lines.append("        failures += 1;")
    lines.append("    }")
    lines.append(f"    println!(\"total_cases={total_cases} failures={{}}\", failures);")
    lines.append("    if failures > 0 { std::process::exit(1); }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_card(spec: dict, provenance: dict) -> dict:
    tool_id = "head_cand_" + spec["id"].replace("-", "_")
    refusals = ["S1_SCHEMA", "S6_CLOSURE_BREACH", "S10_NOT_FOUND", "S11_NOT_REGULAR",
                "S12_ENCODING", "S13_TOOL_INACTIVE", "K4_RESOURCE_LIMIT",
                "K6_DATA_CLASS_UNKNOWN", "K6_SECRET_EGRESS", "K11_ADMISSION_REQUIRED"]
    cases = []
    for case in spec["cases"]:
        expected = case["expect"]
        entry = {
            "id": case["id"],
            "args": {
                "path_ref": {"root_ref": "room:input",
                             "segments": spec["path"]},
                "line_count": case.get("line_count", spec["line_count"]),
                "max_bytes_read": case.get("max_bytes_read", spec["max_bytes_read"]),
            },
        }
        if expected["outcome"] == "ok":
            entry["expected"] = {
                "outcome": "ok",
                "assertions": [
                    f"lines == {len(expected['lines_hex'])}",
                    f"bytes_read == {expected['bytes_read']}",
                    f"truncated == {str(expected['truncated']).lower()}",
                    f"stop_reason == {expected['stop_reason']}",
                ],
            }
        else:
            entry["expected"] = {"outcome": "refusal", "refusal": expected["code"]}
        cases.append(entry)
    # Схема требует не меньше трёх примеров. Добавляем границы карточки, которые
    # не исполняет pure-кандидат: путь вне комнаты и line_count=0.
    if not any(item["id"] == "outside-root" for item in cases):
        cases.append({
            "id": "outside-root",
            "args": {"path_ref": {"root_ref": "host:/", "segments": ["etc", "passwd"]},
                     "line_count": 3, "max_bytes_read": 4096},
            "expected": {"outcome": "refusal", "refusal": "S6_CLOSURE_BREACH"},
        })
    if not any(item["id"] == "count-zero" for item in cases):
        cases.append({
            "id": "count-zero",
            "args": {"path_ref": {"root_ref": "room:input", "segments": spec["path"]},
                     "line_count": 0, "max_bytes_read": spec["max_bytes_read"]},
            "expected": {"outcome": "refusal", "refusal": "S1_SCHEMA"},
        })
    return {
        "schema_version": "tool-card-v1",
        "id": tool_id,
        "kind": "file_read",
        "purpose": (
            "Прочитать не больше N строк и не больше объявленного числа байт "
            "из синтетического fixture класса model_visible; вернуть точную причину остановки."
        ),
        "template": {"id": TEMPLATE, "version": TEMPLATE_VERSION,
                     "slots": ["path_ref", "line_count", "max_bytes_read"]},
        "inputs": [
            {"name": "path_ref", "type": "relative_path", "required": True},
            {"name": "line_count", "type": "bounded_int", "required": True,
             "min": MIN_LINES, "max": MAX_LINES},
            {"name": "max_bytes_read", "type": "bounded_int", "required": True,
             "min": MIN_MAX_BYTES, "max": MAX_MAX_BYTES},
        ],
        "outputs": [
            {"name": "lines", "type": "bounded_list", "required": True, "max": MAX_LINES},
            {"name": "truncated", "type": "truncated", "required": True},
            {"name": "bytes_read", "type": "bounded_int", "required": True,
             "min": 0, "max": MAX_MAX_BYTES},
            {"name": "stop_reason", "type": "enum", "required": True,
             "values": ["eof", "line_cap", "byte_cap", "output_cap"]},
        ],
        "effects": {
            "fs_read": [{"root_ref": "room:input", "segments": ["fixtures"]}],
            "fs_list": [],
            "fs_write": [],
            "bridges": [],
            "process_spawn": False,
            "secret_ops": [],
            "output_channels": ["stdout"],
        },
        "preconditions": [
            {"op": "path_within_root"},
            {"op": "is_regular_file"},
            {"op": "data_class_in", "arg": ["model_visible"]},
        ],
        "postconditions": [
            {"op": "output_truncated_if_more"},
            {"op": "bytes_le", "arg": spec["max_bytes_read"]},
        ],
        "frame_conditions": [{"op": "no_side_effects"}],
        "refusals": refusals,
        "limits": {
            "wall_ms": 2000,
            "cpu_ms": 1000,
            "memory_bytes": 67108864,
            "output_bytes": OUTPUT_BYTES,
            "max_bytes_read": spec["max_bytes_read"],
            "max_files": 1,
            "max_depth": 0,
            "max_open_fds": 16,
            "max_processes": 1,
            "write_bytes": 0,
            "broker_requests": 0,
        },
        "determinism": {"output": "deterministic", "ordering": "input_order",
                        "clock": "none", "randomness": "none"},
        "data_classes": {"accepted_inputs": ["model_visible"],
                         "max_output_class": "model_visible"},
        "secret_refs": [],
        "examples": cases,
        "provenance": provenance,
    }


def render_policy_fragment(spec: dict) -> dict:
    tool_id = "head_cand_" + spec["id"].replace("-", "_")
    rules = [
        {"id": f"{tool_id}-allow-fixtures", "tool": tool_id, "subject": "agent",
         "action": "read", "resource": "file:/mnt/fixtures/**", "effect": "allow",
         "level": "A", "why": "кандидат читает только синтетический fixture"},
        {"id": f"{tool_id}-deny-outside", "tool": tool_id, "subject": "agent",
         "action": "read", "resource": "file:!/mnt/fixtures/**", "effect": "deny",
         "level": "A", "why": "замыкание кандидата — только fixtures"},
        {"id": f"{tool_id}-deny-write", "tool": tool_id, "subject": "agent",
         "action": "write", "resource": "file:/mnt/**", "effect": "deny",
         "level": "A", "why": "чтение не пишет"},
        {"id": f"{tool_id}-deny-net", "tool": tool_id, "subject": "agent",
         "action": "net", "resource": "net:**", "effect": "deny",
         "level": "A", "why": "чтение не требует сети"},
    ]
    return {
        "schema": "herness-policy-fragment-v1",
        "tool": tool_id,
        "rules": rules,
        "merged": False,
        "note": "только кандидат; активная policy не изменена",
    }


def provenance() -> dict:
    return {
        "lawset_digest": digest_file(LAWSET),
        "policy_digest": digest_file(POLICY),
        "room_profile_digest": digest_file(ROOM),
        "schema_digest": digest_file(SCHEMA),
    }


def card_schema_check(card: dict) -> list[str]:
    try:
        import jsonschema
    except Exception:  # noqa: BLE001
        required = json.loads(SCHEMA.read_text(encoding="utf-8"))["required"]
        missing = [field for field in required if field not in card]
        return [f"нет поля {field}" for field in missing]
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(map(str, error.path))}: {error.message}"
            for error in sorted(validator.iter_errors(card), key=lambda item: list(item.path))]


# ------------------------------------------------------------------ generation


def candidate_bytes(spec: dict) -> dict[str, bytes]:
    spec_bytes = canonical(spec) + b"\n"
    source = render_source(spec)
    tests = render_harness([spec])
    card = render_card(spec, provenance())
    card_problems = card_schema_check(card)
    if card_problems:
        raise ValueError("кандидатная карточка не проходит схему: " + "; ".join(card_problems))
    artifacts = {
        "spec.json": spec_bytes,
        "source.rs": source.encode("utf-8"),
        "tests.rs": tests.encode("utf-8"),
        "card.json": (json.dumps(card, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"),
        "policy.fragment.json": (json.dumps(render_policy_fragment(spec), ensure_ascii=False,
                                           indent=1, sort_keys=True) + "\n").encode("utf-8"),
    }
    generation = {
        "schema": "herness-candidate-generation-v1",
        "generator": GENERATOR,
        "template": TEMPLATE,
        "template_version": TEMPLATE_VERSION,
        "spec_id": spec["id"],
        "spec_digest": digest_bytes(spec_bytes),
        "source_digest": digest_bytes(artifacts["source.rs"]),
        "tests_digest": digest_bytes(artifacts["tests.rs"]),
        "card_digest": digest_bytes(artifacts["card.json"]),
        "policy_fragment_digest": digest_bytes(artifacts["policy.fragment.json"]),
        "active": False,
        "admission": None,
        "note": "кандидат; не влит в policy/registry и не имеет допуска",
    }
    artifacts["generation.json"] = (json.dumps(generation, ensure_ascii=False, indent=1,
                                               sort_keys=True) + "\n").encode("utf-8")
    return artifacts


def check_output_root(out: Path) -> None:
    resolved = out.resolve()
    allowed = CANDIDATES.resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise ValueError(f"вывод вне lab/candidates: {resolved}")
    for protected in (POLICY, ROOM, SCHEMA,
                      ROOT / "lab" / "tools" / "registry.jsonl",
                      ROOT / "lab" / "tools" / "registry.events.jsonl",
                      ROOT / "lab" / "tools" / "registry.state.json"):
        if resolved == protected.resolve() or protected.resolve() in resolved.parents:
            raise ValueError(f"запись в защищённый путь запрещена: {protected}")


def write_candidate(spec: dict, out_root: Path) -> dict:
    artifacts = candidate_bytes(spec)
    target = out_root / spec["id"]
    status = "created"
    if target.exists():
        status = "unchanged"
        for name, data in artifacts.items():
            path = target / name
            if not path.exists() or path.read_bytes() != data:
                raise FileExistsError(
                    f"{target} уже существует и отличается ({name}); "
                    "перезапись кандидата запрещена, нужен новый spec id"
                )
    else:
        target.mkdir(parents=True)
        for name, data in artifacts.items():
            (target / name).write_bytes(data)
    return {
        "id": spec["id"],
        "dir": str(target.relative_to(ROOT)).replace("\\", "/"),
        "status": status,
        "digests": {name: digest_bytes(data) for name, data in artifacts.items()},
    }


def check_candidate(spec: dict, out_root: Path) -> list[str]:
    problems = validate_spec(spec)
    if problems:
        return problems
    target = out_root / spec["id"]
    if not target.exists():
        return [f"нет каталога кандидата {target}"]
    try:
        artifacts = candidate_bytes(spec)
    except ValueError as exc:
        return [str(exc)]
    for name, data in artifacts.items():
        path = target / name
        if not path.exists():
            problems.append(f"нет файла {path}")
        elif path.read_bytes() != data:
            problems.append(f"{path} отличается от детерминированной генерации")
    return problems


def collect_specs(directory: Path) -> list[dict]:
    specs = []
    for path in sorted(directory.rglob("*.json")):
        specs.append(load_spec(path))
    return specs


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="генератор кандидатов file_read_stream")
    parser.add_argument("--spec", type=Path, help="один spec JSON")
    parser.add_argument("--all", type=Path, help="каталог со spec JSON")
    parser.add_argument("--out", type=Path, default=OUT_ROOT, help="каталог кандидатов")
    parser.add_argument("--check", action="store_true",
                        help="ничего не писать; сверить спеки и существующие артефакты")
    args = parser.parse_args(argv)

    if bool(args.spec) == bool(args.all):
        parser.error("нужен ровно один из --spec/--all")
    out = args.out
    try:
        check_output_root(out)
    except ValueError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    specs = collect_specs(args.all) if args.all else [load_spec(args.spec)]
    if not specs:
        print("[FAIL] нет спецификаций", file=sys.stderr)
        return 2

    failed = False
    results = []
    for spec in specs:
        problems = validate_spec(spec)
        if problems:
            failed = True
            print(f"[FAIL] {spec.get('id')}: {len(problems)} проблем")
            for problem in problems[:8]:
                print("   -", problem)
            continue
        if args.check:
            problems = check_candidate(spec, out)
            if problems:
                failed = True
                print(f"[FAIL] {spec['id']}: {len(problems)} проблем")
                for problem in problems[:8]:
                    print("   -", problem)
            else:
                results.append({"id": spec["id"], "status": "verified"})
                print(f"[ok] {spec['id']}: кандидат совпадает с генерацией")
        else:
            try:
                result = write_candidate(spec, out)
            except FileExistsError as exc:
                failed = True
                print(f"[FAIL] {spec['id']}: {exc}")
                continue
            results.append(result)
            print(f"[{'ok' if result['status'] in ('created', 'unchanged') else 'FAIL'}] "
                  f"{spec['id']}: {result['status']}")

    print(f"\nспецификаций: {len(specs)}, результатов: {len(results)}, "
          f"провалов: {0 if not failed else 1}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
