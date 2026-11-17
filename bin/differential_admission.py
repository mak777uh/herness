"""Differential admission: Python JCS/verify против независимого Rust-кода.

Зачем: одна реализация не доказывает, что подписанные байты понимаются одинаково.
Здесь два независимых парсера получают одни и те же входы и должны дать тот же
канонический JSON, тот же допуск и тот же отказ. Это не заменяет owner-церемонию
и не делает инструмент active.

    # в WSL/CI, после cargo build --release --bin canonical_check
    python3 bin/differential_admission.py --vectors 64
    python3 bin/differential_admission.py --evidence research/outputs/DIFFERENTIAL-ADMISSION-R1-2026-11-17.txt

На Windows helper не собирается без MSVC/MinGW; инструмент честно откажет,
а не запишет N/A как зелёный.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission as adm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUST = ROOT / "core-rs" / "target" / "release" / (
    "canonical_check.exe" if os.name == "nt" else "canonical_check"
)
NOW = 1780272000  # 2026-06-01T00:00:00Z
RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def run_rust(
    rust: Path, command: str, input_bytes: bytes | None = None, arguments: list[str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(rust), command, *(arguments or [])],
        input=input_bytes,
        capture_output=True,
        timeout=120,
    )


def rust_canonical(rust: Path, raw: bytes) -> tuple[int, bytes, str]:
    result = run_rust(rust, "canonical", input_bytes=raw)
    stderr = result.stderr.decode("utf-8", "replace").strip()
    if result.returncode != 0:
        return result.returncode, b"", stderr
    try:
        return 0, bytes.fromhex(result.stdout.decode("ascii").strip()), stderr
    except (UnicodeDecodeError, ValueError) as exc:
        return 2, b"", f"helper вернул не hex: {exc}"


def rust_verify(
    rust: Path, manifest: Path, sig: Path, anchor: Path, now: int, allow_test_only: bool
) -> tuple[int, dict[str, Any] | None, str]:
    result = run_rust(
        rust,
        "verify",
        arguments=[
            str(manifest),
            str(sig),
            str(anchor),
            str(now),
            "1" if allow_test_only else "0",
        ],
    )
    stderr = result.stderr.decode("utf-8", "replace").strip()
    if result.returncode != 0:
        return result.returncode, None, stderr
    try:
        value = json.loads(result.stdout.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return 2, None, f"helper вернул не JSON: {exc}"
    return 0, value if isinstance(value, dict) else None, stderr


def random_value(rng: random.Random, depth: int = 0) -> Any:
    choices = ["null", "bool", "int", "str"]
    if depth < 3:
        choices += ["list", "dict"]
    kind = rng.choice(choices)
    if kind == "null":
        return None
    if kind == "bool":
        return rng.choice([True, False])
    if kind == "int":
        return rng.choice(
            [0, 1, -1, 7, -42, adm.SAFE_INT, -adm.SAFE_INT, rng.randint(-10_000, 10_000)]
        )
    if kind == "str":
        return rng.choice(
            [
                "",
                "text",
                "текст",
                'quote"',
                "back\\slash",
                "\n\r\t",
                "\u001f",
                "null",
            ]
        )
    if kind == "list":
        return [random_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    keys = rng.sample(
        ["a", "b", "z", "id", "kind", "schema", "value", "x1", "empty"],
        rng.randint(0, 5),
    )
    return {key: random_value(rng, depth + 1) for key in keys}


def canonical_vectors(rust: Path, count: int, seed: int) -> None:
    rng = random.Random(seed)
    passed = 0
    for index in range(count):
        value = random_value(rng)
        raw = json.dumps(value, ensure_ascii=False, indent=1, sort_keys=False).encode("utf-8")
        try:
            parsed = adm.load_json_bytes(raw, "vector")
            expected = adm.canonical(parsed)
        except adm.AdmissionError as exc:
            check(False, f"vector {index}: Python отверг собственный JSON: {exc}")
            continue
        code, actual, error = rust_canonical(rust, raw)
        if code == 0 and actual == expected:
            passed += 1
        else:
            check(
                False,
                f"vector {index}: расхождение canonical: rust rc={code}, "
                f"ожидалось {expected.hex()}, получено {actual.hex()} {error}",
            )
    check(passed == count, f"canonical: {passed}/{count} случайных векторов совпали")

    # Форматирование и порядок ключей не должны влиять: подпись — над canonical.
    value = {"b": [True, None, -3, "текст\n"], "a": {"z": 1, "y": "\u001f"}}
    raw = json.dumps(value, ensure_ascii=False, indent=4).encode("utf-8")
    expected = adm.canonical(value)
    code, actual, error = rust_canonical(rust, raw)
    check(code == 0 and actual == expected, f"pretty JSON сходится с canonical: {error}")

    invalid_cases = [
        ("float", b'{"x":1.5}', "float"),
        ("big int", b'{"x":9007199254740992}', "безопасного диапазона"),
        ("duplicate key", b'{"x":1,"x":2}', "повтор ключа"),
        ("non-ASCII key", b'{"\\u0442":1}', "ASCII"),
    ]
    for label, raw, needle in invalid_cases:
        python_error = ""
        try:
            adm.load_json_bytes(raw, "invalid")
        except adm.AdmissionError as exc:
            python_error = str(exc)
        code, _, rust_error = rust_canonical(rust, raw)
        check(
            bool(python_error) and code != 0,
            f"{label}: Python и Rust отвергли (python={python_error!r}, rust={rust_error!r})",
        )
        if needle:
            check(
                needle in python_error or needle in rust_error,
                f"{label}: причина отказа содержит {needle!r}",
            )


def make_material(directory: Path) -> tuple[Path, Path, str, Path, dict[str, Any]]:
    key_path, anchor_path, fingerprint = adm.create_test_key(directory / "keys")
    key = adm.load_private_key(key_path)
    targets: dict[str, Path] = {}
    for index, field in enumerate(adm.DIGEST_FIELDS):
        target = directory / f"{field}.bin"
        target.write_bytes(f"{field}: vector {index}\n".encode("utf-8"))
        targets[field] = target
    manifest = {
        "schema": "herness-admission-v1",
        "kind": "tool_admission",
        "tool": "head",
        "key_fingerprint": fingerprint,
        "epoch": 1,
        "seq": 1,
        "prev": adm.GENESIS,
        "not_before": "2026-01-01T00:00:00Z",
        "not_after": "2027-01-01T00:00:00Z",
        "test_only": True,
    }
    for field, target in targets.items():
        manifest[field] = adm.digest_file(target)
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sig_path = directory / "manifest.sig"
    sig_path.write_text(adm.sign_manifest(manifest_path.read_bytes(), key) + "\n", encoding="ascii")
    return key_path, anchor_path, fingerprint, manifest_path, manifest


def manifest_vectors(rust: Path, work: Path) -> None:
    key_path, anchor_path, fingerprint, manifest_path, manifest = make_material(work)
    key = adm.load_private_key(key_path)
    anchor_bytes = anchor_path.read_bytes()
    signature = (work / "manifest.sig").read_text(encoding="ascii")

    try:
        python_ok = adm.verify_admission(
            manifest_path.read_bytes(), signature, anchor_bytes, NOW, allow_test_only=True
        )
    except adm.AdmissionError as exc:
        check(False, f"Python не принял собственный манифест: {exc}")
        return
    code, rust_ok, error = rust_verify(rust, manifest_path, work / "manifest.sig", anchor_path, NOW, True)
    check(code == 0 and rust_ok is not None, f"Rust принял test-only манифест: {error}")
    if rust_ok:
        check(
            rust_ok.get("tool") == python_ok["tool"]
            and rust_ok.get("epoch") == python_ok["epoch"]
            and rust_ok.get("seq") == python_ok["seq"]
            and rust_ok.get("test_only") is True
            and rust_ok.get("digests") == python_ok["digests"],
            f"Python/Rust поля допуска совпали: {rust_ok}",
        )
    check(len(fingerprint) == 71, "fingerprint в отчёте, не seed")

    cases: list[tuple[str, bytes, str, int, bool, str]] = []
    raw = manifest_path.read_bytes()
    reordered = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    cases.append(("reordered manifest", reordered, signature, str(anchor_path), NOW, True, "принят"))
    canonical = adm.canonical(manifest)
    mutated = bytearray(canonical)
    position = mutated.find(b'"binary_digest":"sha256:') + len(b'"binary_digest":"sha256:')
    mutated[position] = ord("0") if mutated[position] != ord("0") else ord("1")
    cases.append(("one byte digest", bytes(mutated), signature, str(anchor_path), NOW, True, "K11"))
    bad_sig = ("00" if not signature.startswith("00") else "11") + signature[2:]
    cases.append(("bad signature", raw, bad_sig, str(anchor_path), NOW, True, "K11"))
    cases.append(("expired", raw, signature, str(anchor_path), 1_800_000_000, True, "просрочен"))
    cases.append(("test-only denied", raw, signature, str(anchor_path), NOW, False, "test-only"))
    duplicate = canonical[:-1] + b',"test_only":true}'
    cases.append(("duplicate key", duplicate, signature, str(anchor_path), NOW, True, "повтор ключа"))
    big = json.dumps({**manifest, "seq": 2**53}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    cases.append(("big int", big, signature, str(anchor_path), NOW, True, "безопасного диапазона"))

    for label, raw_case, sig_case, anchor_case, now_case, allow_case, expected in cases:
        case_path = work / f"{label.replace(' ', '-')}.json"
        case_path.write_bytes(raw_case)
        sig_case_path = work / f"{label.replace(' ', '-')}.sig"
        sig_case_path.write_text(sig_case, encoding="ascii")
        try:
            adm.verify_admission(
                raw_case, sig_case, Path(anchor_case).read_bytes(), now_case, allow_test_only=allow_case
            )
            python_code = 0
            python_error = ""
        except adm.AdmissionError as exc:
            python_code = 2
            python_error = str(exc)
        rust_code, _, rust_error = rust_verify(
            rust, case_path, sig_case_path, Path(anchor_case), now_case, allow_case
        )
        both_ok = python_code == 0 and rust_code == 0
        both_refused = python_code != 0 and rust_code != 0
        if expected == "принят":
            check(both_ok, f"{label}: оба приняли; python={python_error!r}, rust={rust_error!r}")
        else:
            check(
                both_refused,
                f"{label}: оба отвергли; python={python_error!r}, rust={rust_error!r}",
            )
            if expected != "K11":
                check(
                    expected in python_error or expected in rust_error,
                    f"{label}: причина содержит {expected!r}; python={python_error!r}, rust={rust_error!r}",
                )

    # Положительная ветка test_only=false на эфемерном ключе: только песочница.
    owner_manifest = dict(manifest)
    owner_manifest["test_only"] = False
    owner_path = work / "owner-manifest.json"
    owner_path.write_text(
        json.dumps(owner_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    owner_sig = adm.sign_manifest(owner_path.read_bytes(), key)
    owner_sig_path = work / "owner-manifest.sig"
    owner_sig_path.write_text(owner_sig + "\n", encoding="ascii")
    try:
        adm.verify_admission(owner_path.read_bytes(), owner_sig, anchor_bytes, NOW, allow_test_only=False)
        python_code = 0
        python_error = ""
    except adm.AdmissionError as exc:
        python_code = 2
        python_error = str(exc)
    rust_code, _, rust_error = rust_verify(rust, owner_path, owner_sig_path, anchor_path, NOW, False)
    check(
        python_code == 0 and rust_code == 0,
        f"test_only=false (эфемерный ключ) принят обоими: python={python_error!r}, rust={rust_error!r}",
    )


def evidence_text(rust: Path, work: Path, checks: int, failed: int) -> str:
    lines = [
        "DIFFERENTIAL-ADMISSION-R1",
        "дата: 2026-11-17",
        f"rust helper: {rust}",
        f"rust digest: {adm.digest_file(rust)}",
        f"рабочий каталог: {work}",
        f"проверок: {checks}; провалов: {failed}",
        "",
        "что доказано:",
        "- Python и Rust дают одинаковые canonical-байты на случайных JCS-векторах;",
        "- повтор ключа, float, big int и не-ASCII ключ отвергаются обоими;",
        "- test-only манифест принимается обоими только с явным allow_test_only;",
        "- правка байта, подписи, срока и повтор ключа отвергаются обоими;",
        "- test_only=false на эфемерном ключе принимается обоими (песочница).",
        "",
        "что это не доказывает:",
        "- что эфемерный ключ является owner-ключом;",
        "- что production registry.active не пуст или что head активирован;",
        "- что полная семантика карточки реализована в promoter;",
        "- что Rust и Python совпадают на всех возможных JSON, кроме проверенных классов;",
        "- K9_proven не выдан.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="differential JCS/admission Python vs Rust")
    parser.add_argument("--rust", default=str(DEFAULT_RUST))
    parser.add_argument("--vectors", type=int, default=32)
    parser.add_argument("--seed", type=int, default=20261117)
    parser.add_argument("--evidence")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)
    rust = Path(args.rust)
    if not rust.is_file():
        print(
            f"DIFFERENTIAL_REFUSED: нет Rust helper {rust}; "
            "собери `cargo build --release --bin canonical_check`",
            file=sys.stderr,
        )
        return 2

    work = Path(tempfile.mkdtemp(prefix="herness-differential-"))
    try:
        canonical_vectors(rust, args.vectors, args.seed)
        manifest_vectors(rust, work)
        failed = sum(1 for flag, _ in RESULTS if not flag)
        for flag, message in RESULTS:
            print(f"[{'ok' if flag else 'FAIL'}] {message}")
        print(f"провалов: {failed}")
        if args.evidence:
            Path(args.evidence).write_text(
                evidence_text(rust, work, len(RESULTS), failed), encoding="utf-8"
            )
            if not args.quiet:
                print(f"evidence: {args.evidence}")
        if args.keep:
            print(f"work: {work}")
        return 0 if failed == 0 else 1
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
