"""HEAD-SLICE-R1: запечатанный прогон `file_read_stream` на хосте и в QEMU/KVM.

Прибор делает три вещи:

1. собирает эфемерный test-only admission и точные checks для card/source/binary/
   fixture/policy/room;
2. запускает один и тот же Rust-бинарь `head_slice_host` на Linux-хосте и как init
   в минимальной QEMU-комнате (`-M microvm -accel kvm`, без сети/диска/host mounts);
3. проверяет 8 критических контролей и дополнительные контроли по точным кодам,
   лимитам и трём детерминированным повторам.

Границы: test-only admission не активирует `head`, не заменяет owner-подпись и не
выдаёт `K9_proven`. Настоящий owner-ключ здесь не создаётся. Секреты не печатаются:
в evidence попадают только пути и fingerprint.

    python bin/head_slice.py --host
    python bin/head_slice.py --qemu
"""

from __future__ import annotations

import argparse
import calendar
import datetime as _datetime
import gzip
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"
sys.path.insert(0, str(BIN))

import admission as adm  # noqa: E402  (bin на пути)
import kvm_probe  # noqa: E402

CORE = ROOT / "core-rs"
CARGO = CORE / "Cargo.toml"
BINARY = CORE / "target" / "release" / "head_slice_host"
FIXTURE = ROOT / "lab" / "fixtures" / "model_visible" / "head-slice.txt"
CARD = ROOT / "lab" / "tools" / "cards" / "head.json"
SOURCE = CORE / "src" / "head.rs"
POLICY = ROOT / "lab" / "tools" / "policy.json"
ROOM_PROFILE = ROOT / "lab" / "tools" / "room-profile-v0.json"
KERNEL = CORE / "boot" / "vmlinuz-lts"
EVIDENCE = ROOT / "research" / "outputs" / "HEAD-SLICE-R1-2026-11-17.txt"
PREREG = ROOT / "lab" / "prereg" / "HEAD-SLICE-R1.json"
MARKER = "HEAD-SLICE-R1"
NOW = calendar.timegm(_datetime.datetime(2026, 11, 17, 12, 0, 0).timetuple())
CANARY = b"CANARY-HEAD-SLICE-OUTSIDE-DO-NOT-READ"


class HarnessError(Exception):
    pass


def wsl_path(path: Path) -> str:
    text = path.resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", text):
        return "/mnt/" + text[0].lower() + text[2:]
    return text


def digest(data: bytes) -> str:
    return adm.digest_bytes(data)


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build_binary() -> dict:
    """Собрать статический бинарь: proc-macro зависимости не должны получать crt-static."""
    env = os.environ.copy()
    env["CARGO_NET_OFFLINE"] = "true"
    commands = [
        ["cargo", "clean", "-p", "hs-core"],
        ["cargo", "build", "--release", "--bin", "head_slice_host"],
        [
            "cargo", "rustc", "--release", "--bin", "head_slice_host", "--",
            "-C", "target-feature=+crt-static",
        ],
    ]
    runs = []
    for command in commands:
        result = subprocess.run(
            command, cwd=CORE, env=env, capture_output=True, text=True
        )
        runs.append({
            "command": " ".join(command),
            "rc": result.returncode,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-4000:],
        })
        if result.returncode != 0:
            raise HarnessError(
                f"сборка не удалась ({result.returncode}): {result.stderr.strip()[-1500:]}"
            )
    if not BINARY.exists():
        raise HarnessError(f"нет бинаря {BINARY}")
    return {"runs": runs, "binary": BINARY, "static": is_static(BINARY)}


def is_static(path: Path) -> bool:
    try:
        result = subprocess.run(["readelf", "-l", str(path)], capture_output=True, text=True)
        if result.returncode == 0:
            return "INTERP" not in result.stdout
    except OSError:
        pass
    try:
        result = subprocess.run(["ldd", str(path)], capture_output=True, text=True)
        return "not a dynamic executable" in (result.stdout + result.stderr)
    except OSError:
        return False


def fixture_manifest(fixture_bytes: bytes, canary: bytes, many: bytes, cr: bytes) -> bytes:
    entries = [
        ("head-slice.txt", len(fixture_bytes), 10, digest(fixture_bytes), "model_visible"),
        ("unclassified.txt", len(b"secret-ish\n"), 1, digest(b"secret-ish\n"), "unknown"),
        ("absent.txt", 1, 1, digest(b"x"), "model_visible"),
        ("dir", 0, 0, digest(b""), "model_visible"),
        ("bad.txt", 2, 1, digest(b"\xff\n"), "model_visible"),
        ("escape", len(canary), 1, digest(canary), "model_visible"),
        ("alias", len(fixture_bytes), 10, digest(fixture_bytes), "model_visible"),
        ("many.txt", len(many), 200, digest(many), "model_visible"),
        ("cr.txt", len(cr), 2, digest(cr), "model_visible"),
    ]
    document = {
        "schema_version": "fixture-manifest-v1",
        "root_ref": "room:input",
        "fixture_root": "fixtures",
        "accepted_classes": ["model_visible"],
        "files": [
            {
                "path": path,
                "bytes": count,
                "lines": lines,
                "sha256": sha,
                "data_class": data_class,
            }
            for path, count, lines, sha, data_class in entries
        ],
    }
    return (json.dumps(document, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def make_admission_manifest(
    artifacts: dict[str, Path],
    anchor_bytes: bytes,
    key,
    not_before: str,
    not_after: str,
    out: Path,
) -> tuple[Path, Path]:
    fingerprint, _public, _min_epoch, _revoked, expected_prev = adm.load_anchor(anchor_bytes)
    document = {
        "schema": "herness-admission-v1",
        "kind": "tool_admission",
        "tool": "head",
        "key_fingerprint": fingerprint,
        "epoch": 1,
        "seq": 1,
        "prev": expected_prev,
        "not_before": not_before,
        "not_after": not_after,
        "test_only": True,
    }
    for field in adm.DIGEST_FIELDS:
        document[field] = adm.digest_file(artifacts[field])
    adm.canonical(document)
    write(out, (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    signature = adm.sign_manifest(out.read_bytes(), key)
    sig = out.with_suffix(".sig")
    write(sig, (signature + "\n").encode("ascii"))
    return out, sig


def prepare(work: Path) -> dict:
    room = work / "room"
    fixtures = room / "fixtures"
    fixtures.mkdir(parents=True)
    fixture_bytes = FIXTURE.read_bytes()
    write(fixtures / "head-slice.txt", fixture_bytes)
    write(fixtures / "unclassified.txt", b"secret-ish\n")
    write(fixtures / "bad.txt", b"\xff\n")
    (fixtures / "dir").mkdir()
    many = b"".join(
        f"line {index:03} 012345678901234567890123456789012345\n".encode()
        for index in range(200)
    )
    write(fixtures / "many.txt", many)
    cr = b"a\r\nb\r\n"
    write(fixtures / "cr.txt", cr)
    canary_text = CANARY + b"\n"
    write(work / "outside-canary.txt", canary_text)

    os.symlink(str(work / "outside-canary.txt"), fixtures / "escape")
    os.symlink("head-slice.txt", fixtures / "alias")

    manifest_bytes = fixture_manifest(fixture_bytes, canary_text, many, cr)
    write(fixtures / "manifest.json", manifest_bytes)
    tampered_manifest = manifest_bytes.replace(b"head-slice.txt", b"head-sliceXtxt", 1)
    write(work / "fixtures" / "tampered.json", tampered_manifest)

    artifacts_dir = work / "artifacts"
    artifacts = {
        "card_digest": artifacts_dir / "card.json",
        "source_digest": artifacts_dir / "head.rs",
        "binary_digest": BINARY,
        "fixture_digest": fixtures / "manifest.json",
        "policy_digest": artifacts_dir / "policy.json",
        "room_digest": artifacts_dir / "room.json",
    }
    write(artifacts["card_digest"], CARD.read_bytes())
    write(artifacts["source_digest"], SOURCE.read_bytes())
    write(artifacts["policy_digest"], POLICY.read_bytes())
    write(artifacts["room_digest"], ROOM_PROFILE.read_bytes())
    tampered_card = work / "artifacts" / "tampered-card.json"
    write(
        tampered_card,
        CARD.read_text(encoding="utf-8").replace('"purpose"', '"purposE"', 1).encode("utf-8"),
    )

    key_path, anchor_path, fingerprint = adm.create_test_key(work / "keys")
    key = adm.load_private_key(key_path)
    anchor_bytes = anchor_path.read_bytes()
    valid_manifest, valid_sig = make_admission_manifest(
        artifacts, anchor_bytes, key,
        "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z",
        work / "admission" / "valid.json",
    )
    expired_manifest, expired_sig = make_admission_manifest(
        artifacts, anchor_bytes, key,
        "2020-01-01T00:00:00Z", "2020-12-31T00:00:00Z",
        work / "admission" / "expired.json",
    )
    corrupt_sig = work / "admission" / "corrupt.sig"
    valid_signature = valid_sig.read_text(encoding="ascii").strip()
    replacement = "0" if valid_signature[0] != "0" else "1"
    write(corrupt_sig, (replacement + valid_signature[1:] + "\n").encode("ascii"))

    return {
        "work": work,
        "room": room,
        "fixtures": fixtures,
        "manifest": fixtures / "manifest.json",
        "tampered_manifest": work / "fixtures" / "tampered.json",
        "artifacts": artifacts,
        "tampered_card": tampered_card,
        "key_path": key_path,
        "anchor": anchor_path,
        "fingerprint": fingerprint,
        "valid_manifest": valid_manifest,
        "valid_sig": valid_sig,
        "expired_manifest": expired_manifest,
        "expired_sig": expired_sig,
        "corrupt_sig": corrupt_sig,
        "fixture_bytes": fixture_bytes,
        "canary": canary_text,
    }


def case_specs() -> list[dict]:
    normal = {
        "path_ref": {"root_ref": "room:input", "segments": ["fixtures", "head-slice.txt"]},
        "line_count": 3,
        "max_bytes_read": 4096,
    }
    return [
        {
            "id": "positive-1", "args": normal, "expect": {
                "outcome": "ok", "lines": 3, "bytes_read": 144,
                "truncated": True, "stop_reason": "line_cap",
            },
        },
        {
            "id": "positive-2", "args": normal, "expect": {
                "outcome": "ok", "lines": 3, "bytes_read": 144,
                "truncated": True, "stop_reason": "line_cap",
            },
        },
        {
            "id": "positive-3", "args": normal, "expect": {
                "outcome": "ok", "lines": 3, "bytes_read": 144,
                "truncated": True, "stop_reason": "line_cap",
            },
        },
        {
            "id": "outside-root",
            "args": {"path_ref": {"root_ref": "host:/", "segments": ["etc", "passwd"]},
                     "line_count": 3, "max_bytes_read": 4096},
            "expect": {"outcome": "refusal", "code": "S6_CLOSURE_BREACH"},
        },
        {
            "id": "dotdot-traversal",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "..", "secret.txt"]},
                     "line_count": 3, "max_bytes_read": 4096},
            "expect": {"outcome": "refusal", "code": "S6_CLOSURE_BREACH"},
        },
        {
            "id": "symlink-outside",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "escape"]},
                     "line_count": 3, "max_bytes_read": 4096},
            "expect": {"outcome": "refusal", "code": "S6_CLOSURE_BREACH"},
        },
        {
            "id": "symlink-inside",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "alias"]},
                     "line_count": 3, "max_bytes_read": 4096},
            "expect": {"outcome": "refusal", "code": "S6_CLOSURE_BREACH"},
        },
        {
            "id": "cap-below-first-line",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "head-slice.txt"]},
                     "line_count": 3, "max_bytes_read": 32},
            "expect": {"outcome": "refusal", "code": "K4_RESOURCE_LIMIT"},
        },
        {
            "id": "zero-line-count",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "head-slice.txt"]},
                     "line_count": 0, "max_bytes_read": 4096},
            "expect": {"outcome": "refusal", "code": "S1_SCHEMA"},
        },
        {
            "id": "unknown-data-class",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "unclassified.txt"]},
                     "line_count": 3, "max_bytes_read": 4096},
            "expect": {"outcome": "refusal", "code": "K6_DATA_CLASS_UNKNOWN"},
        },
        {
            "id": "admission-missing", "args": normal, "admission": None,
            "expect": {"outcome": "refusal", "code": "K11_ADMISSION_REQUIRED"},
        },
        {
            "id": "admission-expired", "args": normal, "admission": "expired",
            "expect": {"outcome": "refusal", "code": "K11_ADMISSION_REQUIRED"},
        },
        {
            "id": "admission-corrupt-signature", "args": normal, "admission": "corrupt",
            "expect": {"outcome": "refusal", "code": "K11_ADMISSION_REQUIRED"},
        },
        {
            "id": "tampered-card", "args": normal, "checks": "tampered-card",
            "expect": {"outcome": "refusal", "code": "K11_ADMISSION_REQUIRED"},
        },
        {
            "id": "tampered-fixture-manifest", "args": normal, "fixture_manifest": "tampered",
            "expect": {"outcome": "refusal", "code": "K11_ADMISSION_REQUIRED"},
        },
        {
            "id": "missing-file",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "absent.txt"]},
                     "line_count": 3, "max_bytes_read": 4096},
            "expect": {"outcome": "refusal", "code": "S10_NOT_FOUND"},
        },
        {
            "id": "not-regular",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "dir"]},
                     "line_count": 3, "max_bytes_read": 4096},
            "expect": {"outcome": "refusal", "code": "S11_NOT_REGULAR"},
        },
        {
            "id": "invalid-utf8",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "bad.txt"]},
                     "line_count": 3, "max_bytes_read": 4096},
            "expect": {"outcome": "refusal", "code": "S12_ENCODING"},
        },
        {
            "id": "outside-canary",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "escape"]},
                     "line_count": 3, "max_bytes_read": 4096},
            "expect": {"outcome": "refusal", "code": "S6_CLOSURE_BREACH"},
        },
        {
            "id": "byte-cap",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "head-slice.txt"]},
                     "line_count": 200, "max_bytes_read": 64},
            "expect": {"outcome": "ok", "lines": 1, "bytes_read": 41,
                       "truncated": True, "stop_reason": "byte_cap"},
        },
        {
            "id": "output-cap",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "many.txt"]},
                     "line_count": 200, "max_bytes_read": 65536},
            "expect": {"outcome": "ok", "truncated": True, "stop_reason": "output_cap"},
        },
        {
            "id": "cr-preserved-eof",
            "args": {"path_ref": {"root_ref": "room:input", "segments": ["fixtures", "cr.txt"]},
                     "line_count": 5, "max_bytes_read": 4096},
            "expect": {"outcome": "ok", "lines": 2, "bytes_read": 6,
                       "truncated": False, "stop_reason": "eof"},
        },
    ]


def make_cases(paths: dict, prefix: str) -> tuple[list[dict], dict]:
    """Собрать кейсы с путями хоста или гостя; вернуть кейсы и expected."""
    checks_base = {
        "card_digest": prefix + "/checks/card.json",
        "source_digest": prefix + "/checks/head.rs",
        "binary_digest": prefix + "/init",
        "fixture_digest": prefix + "/room/fixtures/manifest.json",
        "policy_digest": prefix + "/checks/policy.json",
        "room_digest": prefix + "/checks/room.json",
    }
    valid = {
        "manifest": prefix + "/admission/valid.json",
        "sig": prefix + "/admission/valid.sig",
        "anchor": prefix + "/admission/anchor.json",
    }
    expired = dict(valid, manifest=prefix + "/admission/expired.json",
                   sig=prefix + "/admission/expired.sig")
    corrupt = dict(valid, sig=prefix + "/admission/corrupt.sig")
    tampered_checks = dict(checks_base, card_digest=prefix + "/checks/tampered-card.json")
    cases, expected = [], {}
    for spec in case_specs():
        case = {"id": spec["id"], **spec["args"]}
        if spec.get("admission") is None and "admission" in spec:
            case["admission"] = None
        elif spec.get("admission") == "expired":
            case["admission"] = expired
        elif spec.get("admission") == "corrupt":
            case["admission"] = corrupt
        if spec.get("checks") == "tampered-card":
            case["checks"] = tampered_checks
        if spec.get("fixture_manifest") == "tampered":
            case["fixture_manifest"] = prefix + "/fixtures/tampered.json"
        cases.append(case)
        expected[spec["id"]] = spec["expect"]
    job = {
        "root": prefix + "/room",
        "now_unix": NOW,
        "fixture_manifest": prefix + "/room/fixtures/manifest.json",
        "admission": valid,
        "checks": checks_base,
        "cases": cases,
    }
    return cases, {"job": job, "expected": expected}


def host_job(paths: dict) -> dict:
    prefix = str(paths["work"])
    cases, built = make_cases(paths, prefix)
    job = built["job"]
    # Пути хоста строятся из work/..., но имена каталогов в make_cases ожидают
    # структуру /checks, /admission, /fixtures. Проверим и перезапишем явно.
    job["root"] = str(paths["room"])
    job["fixture_manifest"] = str(paths["manifest"])
    job["admission"] = {
        "manifest": str(paths["valid_manifest"]),
        "sig": str(paths["valid_sig"]),
        "anchor": str(paths["anchor"]),
    }
    job["checks"] = {
        "card_digest": str(paths["artifacts"]["card_digest"]),
        "source_digest": str(paths["artifacts"]["source_digest"]),
        "binary_digest": str(paths["artifacts"]["binary_digest"]),
        "fixture_digest": str(paths["artifacts"]["fixture_digest"]),
        "policy_digest": str(paths["artifacts"]["policy_digest"]),
        "room_digest": str(paths["artifacts"]["room_digest"]),
    }
    for case in cases:
        case_id = case["id"]
        if case_id == "admission-expired":
            case["admission"] = {
                "manifest": str(paths["expired_manifest"]),
                "sig": str(paths["expired_sig"]),
                "anchor": str(paths["anchor"]),
            }
        elif case_id == "admission-corrupt-signature":
            case["admission"] = {
                "manifest": str(paths["valid_manifest"]),
                "sig": str(paths["corrupt_sig"]),
                "anchor": str(paths["anchor"]),
            }
        elif case_id == "tampered-card":
            case["checks"] = dict(job["checks"], card_digest=str(paths["tampered_card"]))
        elif case_id == "tampered-fixture-manifest":
            case["fixture_manifest"] = str(paths["tampered_manifest"])
    return {"cases": cases, "job": job, "expected": built["expected"]}


def run_binary(job_path: Path, guest: bool = False) -> dict:
    command = [str(BINARY), "--job", str(job_path)]
    if guest:
        command.append("--guest")
    started = time.time()
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    combined = (result.stdout or "") + (result.stderr or "")
    records = []
    for line in combined.replace("\r", "").splitlines():
        if MARKER not in line:
            continue
        raw = line.split(MARKER, 1)[1].strip()
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError:
            records.append({"id": "__parse__", "outcome": "error", "error": raw})
    return {
        "command": command,
        "rc": result.returncode,
        "seconds": round(time.time() - started, 3),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "records": records,
        "combined": combined,
    }


def verify_records(records: list[dict], expected: dict, cases: list[dict], combined: str) -> list[str]:
    problems: list[str] = []
    by_id = {}
    for record in records:
        if record.get("id") == "__summary__":
            continue
        if record.get("id") in by_id:
            problems.append(f"повтор результата id={record.get('id')}")
        by_id[record.get("id")] = record
    summary = next((item for item in records if item.get("id") == "__summary__"), None)
    if summary is None:
        problems.append("нет __summary__")
    else:
        if summary.get("cases") != len(cases):
            problems.append(f"summary cases={summary.get('cases')} != {len(cases)}")
        if summary.get("duplicates"):
            problems.append(f"summary duplicates={summary.get('duplicates')}")
    if CANARY.decode() in combined.replace("\r", ""):
        problems.append("canary вне корня попала в вывод")
    requests = {case["id"]: case for case in cases}
    for case_id, expectation in expected.items():
        record = by_id.get(case_id)
        if record is None:
            problems.append(f"{case_id}: нет результата")
            continue
        outcome = record.get("outcome")
        if outcome != expectation.get("outcome"):
            problems.append(
                f"{case_id}: outcome={outcome!r}, ждали {expectation.get('outcome')!r}; "
                f"error={record.get('error')!r}"
            )
            continue
        if outcome == "refusal":
            if record.get("code") != expectation.get("code"):
                problems.append(
                    f"{case_id}: code={record.get('code')!r}, ждали {expectation.get('code')!r}"
                )
            continue
        if outcome != "ok":
            problems.append(f"{case_id}: неизвестный outcome {outcome!r}")
            continue
        for field in ("lines", "bytes_read", "truncated", "stop_reason"):
            if field not in expectation:
                continue
            if field == "lines":
                actual = len(record.get("lines", [])) if isinstance(record.get("lines"), list) else None
            else:
                actual = record.get(field)
            if actual != expectation[field]:
                problems.append(
                    f"{case_id}: {field}={actual!r}, ждали {expectation[field]!r}"
                )
        request = requests[case_id]
        max_bytes = request.get("max_bytes_read")
        line_count = request.get("line_count")
        bytes_read = record.get("bytes_read")
        received = record.get("bytes_received")
        lines = record.get("lines")
        if not isinstance(bytes_read, int) or bytes_read < 0:
            problems.append(f"{case_id}: bytes_read не целое")
        elif max_bytes is not None and bytes_read > max_bytes:
            problems.append(f"{case_id}: bytes_read={bytes_read} > max={max_bytes}")
        if bytes_read is not None and bytes_read > 8192:
            problems.append(f"{case_id}: bytes_read={bytes_read} > output_bytes=8192")
        if not isinstance(received, int) or received < 0:
            problems.append(f"{case_id}: bytes_received не диагностическое целое")
        elif max_bytes is not None and received > max_bytes:
            problems.append(f"{case_id}: bytes_received={received} > max={max_bytes}")
        if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
            problems.append(f"{case_id}: lines не список строк")
        elif line_count is not None and len(lines) > line_count:
            problems.append(f"{case_id}: lines={len(lines)} > line_count={line_count}")
        stop = record.get("stop_reason")
        truncated = record.get("truncated")
        if isinstance(stop, str) and isinstance(truncated, bool):
            if truncated != (stop != "eof"):
                problems.append(f"{case_id}: truncated={truncated} не согласован со stop={stop}")
        else:
            problems.append(f"{case_id}: нет stop_reason/truncated")
    positives = [by_id.get(f"positive-{index}") for index in (1, 2, 3)]
    if all(item is not None for item in positives):
        first = {key: positives[0].get(key) for key in
                 ("lines", "bytes_read", "truncated", "stop_reason")}
        for index, item in enumerate(positives[1:], 2):
            again = {key: item.get(key) for key in
                     ("lines", "bytes_read", "truncated", "stop_reason")}
            if again != first:
                problems.append(f"positive-{index}: повтор отличается от positive-1")
    else:
        problems.append("нет трёх повторов normal")
    return problems


def host_result(paths: dict, build: dict) -> dict:
    built = host_job(paths)
    job_path = paths["work"] / "job-host.json"
    write(job_path, (json.dumps(built["job"], ensure_ascii=False, indent=2) + "\n").encode())
    run = run_binary(job_path)
    problems = verify_records(run["records"], built["expected"], built["cases"], run["combined"])
    if not is_static(BINARY):
        problems.append("бинарь не static; QEMU-гость не сможет загрузиться без libs")
    return {"built": built, "run": run, "problems": problems, "job_path": job_path}


def guest_entries(paths: dict, job_bytes: bytes) -> list[tuple[str, bytes, int]]:
    entries: list[tuple[str, bytes, int]] = [
        ("dev", b"", 0o040755),
        ("proc", b"", 0o040755),
        ("sys", b"", 0o040755),
        ("room", b"", 0o040755),
        ("room/fixtures", b"", 0o040755),
        ("room/fixtures/dir", b"", 0o040755),
        ("checks", b"", 0o040755),
        ("admission", b"", 0o040755),
        ("fixtures", b"", 0o040755),
        ("init", BINARY.read_bytes(), 0o100755),
        ("job.json", job_bytes, 0o100644),
    ]
    for name in ("head-slice.txt", "unclassified.txt", "bad.txt", "many.txt", "cr.txt", "manifest.json"):
        entries.append((f"room/fixtures/{name}", (paths["fixtures"] / name).read_bytes(), 0o100644))
    entries.append(("room/fixtures/alias", b"head-slice.txt", 0o120777))
    entries.append(("room/fixtures/escape", b"/outside-canary.txt", 0o120777))
    entries.append(("outside-canary.txt", paths["canary"], 0o100644))
    entries.append(("fixtures/tampered.json", paths["tampered_manifest"].read_bytes(), 0o100644))
    for source, name in (
        (paths["artifacts"]["card_digest"], "card.json"),
        (paths["artifacts"]["source_digest"], "head.rs"),
        (paths["artifacts"]["policy_digest"], "policy.json"),
        (paths["artifacts"]["room_digest"], "room.json"),
        (paths["tampered_card"], "tampered-card.json"),
    ):
        entries.append((f"checks/{name}", source.read_bytes(), 0o100644))
    for source, name in (
        (paths["valid_manifest"], "valid.json"),
        (paths["valid_sig"], "valid.sig"),
        (paths["expired_manifest"], "expired.json"),
        (paths["expired_sig"], "expired.sig"),
        (paths["corrupt_sig"], "corrupt.sig"),
        (paths["anchor"], "anchor.json"),
    ):
        entries.append((f"admission/{name}", source.read_bytes(), 0o100644))
    return entries


def guest_job(paths: dict) -> dict:
    cases, built = make_cases(paths, "")
    job = built["job"]
    for case in cases:
        if case["id"] == "admission-expired":
            case["admission"] = {
                "manifest": "/admission/expired.json",
                "sig": "/admission/expired.sig",
                "anchor": "/admission/anchor.json",
            }
        elif case["id"] == "admission-corrupt-signature":
            case["admission"] = {
                "manifest": "/admission/valid.json",
                "sig": "/admission/corrupt.sig",
                "anchor": "/admission/anchor.json",
            }
    return {"cases": cases, "job": job, "expected": built["expected"]}


def run_guest(paths: dict, build: dict) -> dict:
    built = guest_job(paths)
    job_bytes = (json.dumps(built["job"], ensure_ascii=False, indent=2) + "\n").encode()
    archive = kvm_probe.cpio_newc(guest_entries(paths, job_bytes))
    initrd = paths["work"] / "head-slice-initramfs.cpio.gz"
    initrd.write_bytes(gzip.compress(archive, 9))
    qmp = paths["work"] / "qmp-head.sock"
    instance, trace_error = kvm_probe.start_trace()
    command = kvm_probe.qemu_command(KERNEL, initrd, qmp)
    forbidden = [
        token for token in ("-drive", "-fsdev", "-virtfs", "-netdev", "hostfwd",
                            "9p", "virtiofs", "user,")
        if token in " ".join(command)
    ]
    started = time.time()
    process = None
    stdout = stderr = b""
    qmp_answer = None
    qmp_error = ""
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        qmp_answer, qmp_error = kvm_probe.qmp_query_kvm(qmp)
        try:
            stdout, stderr = process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
    finally:
        kvm_count = kvm_probe.trace_count(instance)
        kvm_probe.stop_trace(instance)
    combined = (stdout or b"").decode("utf-8", "replace") + (stderr or b"").decode("utf-8", "replace")
    records = []
    for line in combined.replace("\r", "").splitlines():
        if MARKER not in line:
            continue
        raw = line.split(MARKER, 1)[1].strip()
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError:
            records.append({"id": "__parse__", "outcome": "error", "error": raw})
    problems = verify_records(records, built["expected"], built["cases"], combined)
    if forbidden:
        problems.append(f"в команде QEMU есть запрещённые устройства: {forbidden}")
    if process is None or process.returncode not in (0, kvm_probe.EXIT_VALUE << 1 | 1):
        problems.append(f"QEMU rc={None if process is None else process.returncode}")
    answer = qmp_answer.get("return") if isinstance(qmp_answer, dict) else None
    if not isinstance(answer, dict) or answer.get("present") is not True or answer.get("enabled") is not True:
        problems.append(f"QMP query-kvm: {qmp_answer!r} ({qmp_error or 'нет ответа'})")
    if trace_error:
        problems.append(f"trace: {trace_error}")
    if kvm_count <= 0:
        problems.append("kvm:kvm_entry не сработал: KVM_RUN не наблюдался")
    return {
        "built": built,
        "command": command,
        "rc": None if process is None else process.returncode,
        "seconds": round(time.time() - started, 3),
        "stdout": combined,
        "records": records,
        "stdout_digest": digest(combined.encode("utf-8")),
        "qmp": qmp_answer,
        "qmp_error": qmp_error,
        "trace_error": trace_error,
        "kvm_entry": kvm_count,
        "problems": problems,
        "forbidden": forbidden,
        "initrd": initrd,
        "forbidden_count": len(forbidden),
    }


def environment(build: dict, guest: dict | None) -> dict:
    def run(command: list[str]) -> str:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            return (result.stdout or result.stderr).strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError) as error:
            return f"N/A: {error}"

    return {
        "host": platform.platform(),
        "kernel": run(["uname", "-a"]),
        "qemu": run([kvm_probe.QEMU, "--version"]),
        "rustc": run(["rustc", "--version"]),
        "cargo": run(["cargo", "--version"]),
        "binary_static": str(is_static(BINARY)),
        "build_static": str(build.get("static")),
        "guest_kvm_entry": "N/A" if guest is None else str(guest["kvm_entry"]),
        "guest_qmp": "N/A" if guest is None else json.dumps(guest["qmp"], ensure_ascii=False),
    }


def guest_table(records: list[dict]) -> list[str]:
    lines = []
    for record in records:
        case_id = record.get("id", "<без id>")
        if case_id in ("__summary__", "__setup__", "__parse__"):
            continue
        if record.get("outcome") == "refusal":
            lines.append(f"- {case_id}: refusal `{record.get('code')}`")
        else:
            lines.append(
                f"- {case_id}: ok lines={len(record.get('lines', []))} "
                f"bytes_read={record.get('bytes_read')} "
                f"bytes_received={record.get('bytes_received')} "
                f"truncated={str(record.get('truncated')).lower()} "
                f"stop_reason={record.get('stop_reason')}"
            )
    return lines


def evidence_text(paths: dict, build: dict, host: dict, guest: dict | None, env: dict) -> str:
    problems = list(host["problems"])
    if guest is not None:
        problems += guest["problems"]
    verdict = "PASS" if not problems else "FAIL"
    mode = "host + QEMU/KVM" if guest is not None else "host only (QEMU N/A)"
    checks = {field: digest(paths["artifacts"][field].read_bytes()) for field in adm.DIGEST_FIELDS}
    lines = [
        "# HEAD-SLICE-R1 — ограниченное чтение и admission",
        "",
        f"Режим: {mode}",
        f"Вердикт: {verdict}",
        "Пре-регистрация: `lab/prereg/HEAD-SLICE-R1.json`; решения: `docs/DECISIONS-R8-2026-11-17.md`.",
        "",
        "## Точные байты",
        "",
        *[f"- {field}: `{value}` (`{paths['artifacts'][field]}`)" for field, value in checks.items()],
        f"- fixture: `{digest(paths['fixture_bytes'])}` ({len(paths['fixture_bytes'])} B, "
        "10 строк, синтетический model_visible)",
        f"- test-only key fingerprint: `{paths['fingerprint']}` (seed не печатается)",
        "",
        "## Среда",
        "",
        *[f"- {key}: {value}" for key, value in env.items()],
        "",
        "## Сборка",
        "",
        "```text",
        *[f"{item['command']}  # rc={item['rc']}" for item in build["runs"]],
        "```",
        "",
        "## Хост",
        "",
        f"Команда: `{' '.join(host['run']['command'])}`",
        f"rc: {host['run']['rc']}",
        f"время: {host['run']['seconds']} с",
        "```json",
        json.dumps(host["run"]["records"], ensure_ascii=False, indent=1),
        "```",
        "",
    ]
    if guest is not None:
        lines += [
            "## QEMU/KVM",
            "",
            "```text",
            " ".join(guest["command"]),
            "```",
            f"rc: {guest['rc']} (0 = poweroff, 33 = isa-debug-exit; оба — не TCG)",
            f"время: {guest['seconds']} с",
            f"QMP query-kvm: {json.dumps(guest['qmp'], ensure_ascii=False)}",
            f"kvm:kvm_entry: {guest['kvm_entry']}",
            "KVM_RUN отдельно подтверждён `research/kvm/KVM-RUN-2026-11-17.txt`; счётчики",
            "разных прогонов не обязаны совпадать.",
            f"guest stdout digest: `{guest['stdout_digest']}`",
            f"запрещённые устройства в команде: {guest['forbidden']}",
            "",
            "Гость печатал те же JSON-строки; хост проверил их тем же `verify_records`.",
            "Сеть/диск/host mounts отсутствуют в команде; это проверка конфигурации, не",
            "доказательство безопасности комнаты.",
            "",
            "### Результаты гостя",
            "",
            *guest_table(guest["records"]),
            "",
        ]
    lines += [
        "## Проверки",
        "",
        "- 8 критических контролей: точные коды S6/S1/K4/K6/K11.",
        "- Нормальный fixture: 3 строки, bytes_read=144, truncated=true, stop_reason=line_cap.",
        "- Три повтора normal совпадают по lines/bytes_read/truncated/stop_reason.",
        "- bytes_read <= max_bytes_read и <= output_bytes=8192 во всех ok-прогонах.",
        "- canary вне корня не попала в вывод.",
        "- tampered card / fixture manifest / signature → K11.",
        "- byte cap, output cap, CR и EOF проверены отдельными кейсами.",
        "- S10/S11/S12 — отдельные объектные/кодировочные отказы.",
        "",
        "## Что это НЕ доказывает",
        "",
        "- Owner-подписи нет: admission test-only, `head` не активирован.",
        "- Полная семантика карточки/promoter и Windows-launch не проверялись этим срезом.",
        "- Гость не является доказанной границей безопасности: измерены коды и отсутствие",
        "  запрещённых устройств в команде, а не изоляция ядра/железа.",
        "- `K9_proven` не выдан.",
        "",
    ]
    if problems:
        lines += ["## Провалы", "", *[f"- {problem}" for problem in problems], ""]
    return "\n".join(lines)


def update_prereg(ok: bool, evidence: Path) -> None:
    data = json.loads(PREREG.read_text(encoding="utf-8"))
    data["closed"] = ok
    data["updated"] = "2026-11-17"
    if ok:
        data["conclusion"] = (
            "PASS: все 8 критических контролей отвергнуты точными кодами; normal 3/144/truncated; "
            "3 повтора детерминированы; host+QEMU/KVM evidence связан digest'ами; "
            "test-only admission не активирует head"
        )
        data["evidence"] = str(evidence.relative_to(ROOT)).replace("\\", "/")
        data["closed_date"] = "2026-11-17"
    else:
        data.pop("conclusion", None)
    PREREG.write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def run_host_mode(paths: dict, build: dict, keep: bool) -> int:
    host = host_result(paths, build)
    env = environment(build, None)
    text = evidence_text(paths, build, host, None, env)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(text, encoding="utf-8")
    print(f"HEAD-SLICE-R1 host: {'PASS' if not host['problems'] else 'FAIL'}")
    for problem in host["problems"]:
        print(f"  [FAIL] {problem}")
    print(f"evidence: {EVIDENCE}")
    if not keep:
        shutil.rmtree(paths["work"], ignore_errors=True)
    return 0 if not host["problems"] else 1


def run_qemu_mode(paths: dict, build: dict, keep: bool) -> int:
    host = host_result(paths, build)
    guest = run_guest(paths, build)
    env = environment(build, guest)
    problems = host["problems"] + guest["problems"]
    text = evidence_text(paths, build, host, guest, env)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(text, encoding="utf-8")
    update_prereg(not problems, EVIDENCE)
    print(f"HEAD-SLICE-R1 host+QEMU: {'PASS' if not problems else 'FAIL'}")
    for problem in problems:
        print(f"  [FAIL] {problem}")
    print(f"kvm:kvm_entry={guest['kvm_entry']}, qemu rc={guest['rc']}")
    print(f"evidence: {EVIDENCE}")
    if not keep:
        shutil.rmtree(paths["work"], ignore_errors=True)
    return 0 if not problems else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="store_true", help="быстрый прогон на Linux-хосте")
    parser.add_argument("--qemu", action="store_true", help="прогон в QEMU microvm с KVM")
    parser.add_argument("--keep", action="store_true", help="оставить временные файлы")
    parser.add_argument("--no-build", action="store_true", help="не собирать бинарь")
    args = parser.parse_args(argv)
    if not args.host and not args.qemu:
        parser.error("нужен --host или --qemu")

    if os.name == "nt":
        command = [
            "wsl", "-d", "Ubuntu", "-u", "root", "--exec", "python3",
            wsl_path(Path(__file__)), *sys.argv[1:],
        ]
        return subprocess.run(command).returncode

    if platform.system() != "Linux":
        raise HarnessError("HEAD-SLICE-R1 требует Linux (openat2); Windows запускает WSL")

    work = Path(tempfile.mkdtemp(prefix="herness-head-slice-"))
    build = {"runs": [], "binary": BINARY, "static": is_static(BINARY)}
    try:
        if not args.no_build:
            build = build_binary()
        elif not BINARY.exists():
            raise HarnessError(f"нет бинаря {BINARY}; уберите --no-build")
        paths = prepare(work)
        if args.qemu:
            return run_qemu_mode(paths, build, args.keep)
        return run_host_mode(paths, build, args.keep)
    except HarnessError as error:
        print(f"HEAD-SLICE-R1: FAIL: {error}", file=sys.stderr)
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
