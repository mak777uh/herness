"""Admission v0: JCS-подмножество, detached Ed25519 и exact-byte digest.

Границы:
- настоящий owner-ключ здесь не создаётся; `keygen` требует `--test-only` и
  отказывается писать ключ внутрь репозитория;
- в отчётах печатается только fingerprint, не private seed;
- манифест с `test_only=true` не даёт права запуска без явного `--allow-test-only`
  и никогда не делает инструмент `active`;
- любая ошибка — `K11_ADMISSION_REQUIRED`, а не частичный допуск.

Контракт: `docs/DECISIONS-R8-2026-11-17.md` (A01/Q15); Rust-проверка —
`core-rs/src/admission.rs`.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as _datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
except Exception as exc:  # pragma: no cover - окружение без cryptography
    raise SystemExit(f"K11_ADMISSION_REQUIRED: нет cryptography для Ed25519: {exc}")

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = b"herness-admission-v1"
GENESIS = "sha256:ad91748e7797e06cd9bade33556abe349c5b6f8ad15fd51384ffe1822a889b68"
DIGEST_FIELDS = (
    "card_digest",
    "source_digest",
    "binary_digest",
    "fixture_digest",
    "policy_digest",
    "room_digest",
)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TOOL_RE = re.compile(r"^[a-z0-9_]{1,64}$")
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SAFE_INT = 2**53 - 1


class AdmissionError(Exception):
    pass


def refuse(reason: str) -> "AdmissionError":
    return AdmissionError(f"K11_ADMISSION_REQUIRED: {reason}")


def _reject_float(_text: str) -> Any:
    raise refuse("float в каноническом JSON запрещён")


def _reject_constant(_text: str) -> Any:
    raise refuse("NaN/Infinity в JSON запрещены")


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """JSON-объект без повторов ключей.

    `json.loads` по умолчанию берёт последнее значение, поэтому два разных
    парсера могут прочитать один и тот же подписанный файл по-разному.
    Повтор ключа — отказ, а не выбор победителя.
    """
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise refuse(f"повтор ключа {key!r} в JSON запрещён")
        result[key] = value
    return result


def load_json_bytes(data: bytes, what: str) -> Any:
    try:
        document = json.loads(
            data.decode("utf-8"),
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_pairs_without_duplicates,
        )
    except AdmissionError:
        raise
    except Exception as exc:
        raise refuse(f"{what} не разбирается как JSON: {exc}") from exc
    # Та же строгость, что и при подписи: до проверки подписи документ должен
    # лежать в JCS-подмножестве, иначе разные парсеры увидят разные числа.
    _check_canonical_subset(document)
    return document


def _check_canonical_subset(value: Any) -> None:
    if isinstance(value, float):
        raise refuse("float в каноническом JSON запрещён")
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        if abs(value) > SAFE_INT:
            raise refuse(
                f"целое {value} вне безопасного диапазона JCS (±{SAFE_INT}): "
                "сравнение через парсеры неоднозначно"
            )
        return
    if isinstance(value, list):
        for item in value:
            _check_canonical_subset(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise refuse("ключ канонического JSON должен быть строкой")
            if not key.isascii():
                raise refuse("не-ASCII ключ не входит в JCS-подмножество v0")
            _check_canonical_subset(item)
        return
    raise refuse(f"тип {type(value).__name__} не входит в JCS-подмножество")


def canonical(value: Any) -> bytes:
    """JCS-подмножество v0: без float, ключи отсортированы, UTF-8."""
    _check_canonical_subset(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
    except OSError as exc:
        raise refuse(f"нет файла {path}: {exc}") from exc
    return "sha256:" + hasher.hexdigest()


def verify_file_digest(expected: str, path: Path) -> None:
    actual = digest_file(path)
    if actual != expected:
        raise refuse(f"{path} не совпадает с допущенными байтами: ожидалось {expected}, получено {actual}")


def parse_time(value: str, field: str) -> int:
    if not isinstance(value, str) or not TIME_RE.match(value):
        raise refuse(f"manifest: {field} не UTC RFC3339 (YYYY-MM-DDTHH:MM:SSZ)")
    try:
        parsed = _datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise refuse(f"manifest: {field} вне календаря: {exc}") from exc
    return calendar.timegm(parsed.timetuple())


def _text(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise refuse(f"нет строкового поля {key}")
    return value


def _integer(obj: dict[str, Any], key: str) -> int:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise refuse(f"нет целого поля {key}")
    return value


def _boolean(obj: dict[str, Any], key: str) -> bool:
    value = obj.get(key)
    if not isinstance(value, bool):
        raise refuse(f"нет булева поля {key}")
    return value


def public_bytes(key: Ed25519PrivateKey) -> bytes:
    try:
        return key.public_key().public_bytes_raw()
    except AttributeError:  # cryptography < 41
        from cryptography.hazmat.primitives import serialization

        return key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )


def load_anchor(data: bytes) -> tuple[str, bytes, int, list[int], str]:
    document = load_json_bytes(data, "anchor")
    if not isinstance(document, dict):
        raise refuse("anchor должен быть объектом")
    if _text(document, "schema") != "herness-anchor-v1":
        raise refuse("anchor: ожидалась схема herness-anchor-v1")
    if _text(document, "kind") != "owner_anchor":
        raise refuse("anchor: ожидался kind owner_anchor")
    try:
        public = bytes.fromhex(_text(document, "public_key"))
    except ValueError as exc:
        raise refuse(f"anchor: public_key не hex: {exc}") from exc
    if len(public) != 32:
        raise refuse("anchor: public_key не 32 байта")
    fingerprint = digest_bytes(public)
    if _text(document, "key_fingerprint") != fingerprint:
        raise refuse("anchor: fingerprint не совпадает с public_key")
    min_epoch = _integer(document, "min_epoch")
    if min_epoch < 0:
        raise refuse("anchor: min_epoch отрицателен")
    revoked_raw = document.get("revoked_epochs")
    if not isinstance(revoked_raw, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in revoked_raw
    ):
        raise refuse("anchor: revoked_epochs должен быть массивом целых")
    expected_prev = document.get("expected_prev", GENESIS)
    if not isinstance(expected_prev, str) or not DIGEST_RE.match(expected_prev):
        raise refuse("anchor: expected_prev не sha256")
    return fingerprint, public, min_epoch, list(revoked_raw), expected_prev


def verify_admission(
    manifest_bytes: bytes,
    signature_hex: str,
    anchor_bytes: bytes,
    now_unix: int,
    allow_test_only: bool = False,
) -> dict[str, Any]:
    manifest = load_json_bytes(manifest_bytes, "manifest")
    fingerprint, public, min_epoch, revoked, expected_prev = load_anchor(anchor_bytes)
    if not isinstance(manifest, dict):
        raise refuse("manifest должен быть объектом")
    if _text(manifest, "schema") != "herness-admission-v1":
        raise refuse("manifest: ожидалась схема herness-admission-v1")
    if _text(manifest, "kind") != "tool_admission":
        raise refuse("manifest: ожидался kind tool_admission")
    tool = _text(manifest, "tool")
    if not TOOL_RE.match(tool):
        raise refuse("manifest: недопустимое имя инструмента")
    if _text(manifest, "key_fingerprint") != fingerprint:
        raise refuse("manifest: key_fingerprint не совпадает с anchor")

    digests: dict[str, str] = {}
    for field in DIGEST_FIELDS:
        value = _text(manifest, field)
        if not DIGEST_RE.match(value):
            raise refuse(f"manifest: {field} не sha256:<lowercase hex>")
        digests[field] = value

    epoch = _integer(manifest, "epoch")
    seq = _integer(manifest, "seq")
    if epoch < 1 or seq < 1:
        raise refuse("manifest: epoch и seq должны быть >= 1")
    if epoch < min_epoch:
        raise refuse(f"manifest: epoch {epoch} ниже min_epoch {min_epoch} (rollback)")
    if epoch in revoked:
        raise refuse(f"manifest: epoch {epoch} отозван")
    prev = _text(manifest, "prev")
    if not DIGEST_RE.match(prev):
        raise refuse("manifest: prev не sha256")
    if prev != expected_prev:
        raise refuse("manifest: prev не совпадает с якорем (разрыв цепочки)")

    not_before = parse_time(_text(manifest, "not_before"), "not_before")
    not_after = parse_time(_text(manifest, "not_after"), "not_after")
    if not_after < not_before:
        raise refuse("manifest: not_after раньше not_before")
    if now_unix < not_before:
        raise refuse("manifest: admission ещё не вступил в силу")
    if now_unix > not_after:
        raise refuse("manifest: admission просрочен")

    test_only = _boolean(manifest, "test_only")
    if test_only and not allow_test_only:
        raise refuse("manifest: test-only не даёт права запуска; нужен owner-подписанный admission")

    try:
        signature = bytes.fromhex(signature_hex.strip())
    except ValueError as exc:
        raise refuse(f"подпись не hex: {exc}") from exc
    if len(signature) != 64:
        raise refuse("подпись не 64 байта")

    signed = DOMAIN + b"\n" + canonical(manifest)
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(signature, signed)
    except Exception as exc:
        raise refuse(f"подпись не соответствует манифесту и anchor: {exc}") from exc

    return {
        "schema": "herness-admission-v1",
        "kind": "tool_admission",
        "tool": tool,
        "epoch": epoch,
        "seq": seq,
        "test_only": test_only,
        "key_fingerprint": fingerprint,
        "digests": digests,
        "signature_ok": True,
        "validity_ok": True,
    }


def verify_checks(manifest: dict[str, Any], checks: list[str]) -> None:
    if not checks:
        return
    seen: set[str] = set()
    for item in checks:
        if "=" not in item:
            raise refuse(f"--check ожидает name=path, получено {item!r}")
        name, raw_path = item.split("=", 1)
        if name not in DIGEST_FIELDS:
            raise refuse(f"--check: неизвестное поле {name}")
        if name in seen:
            raise refuse(f"--check: поле {name} повторено")
        seen.add(name)
        expected = manifest["digests"][name]
        verify_file_digest(expected, Path(raw_path))


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


def _write_private_seed(path: Path, seed: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, seed.hex().encode("ascii") + b"\n")
    finally:
        os.close(fd)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def create_ephemeral_key(directory: Path, test_only: bool, name: str) -> tuple[Path, Path, str]:
    """Создать эфемерный ключ вне репозитория; `test_only` — объявление anchor, не сила ключа.

    Настоящий owner-ключ через CLI не создаётся: эта функция нужна песочным приборам,
    чтобы проверить положительную ветку допуска. Seed не печатается.
    """
    if _inside_repo(directory):
        raise refuse("private key не может лежать внутри репозитория")
    directory.mkdir(parents=True, exist_ok=True)
    key_path = directory / f"{name}.seed"
    anchor_path = directory / "anchor.json"
    if key_path.exists() or anchor_path.exists():
        raise refuse(f"файлы ключа уже существуют в {directory}")
    seed = secrets.token_bytes(32)
    key = Ed25519PrivateKey.from_private_bytes(seed)
    public = public_bytes(key)
    fingerprint = digest_bytes(public)
    _write_private_seed(key_path, seed)
    anchor = {
        "schema": "herness-anchor-v1",
        "kind": "owner_anchor",
        "public_key": public.hex(),
        "key_fingerprint": fingerprint,
        "min_epoch": 1,
        "revoked_epochs": [],
        "expected_prev": GENESIS,
        "test_only": bool(test_only),
    }
    anchor_path.write_text(
        json.dumps(anchor, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return key_path, anchor_path, fingerprint


def create_test_key(directory: Path) -> tuple[Path, Path, str]:
    return create_ephemeral_key(directory, test_only=True, name="test-only")


def load_private_key(path: Path) -> Ed25519PrivateKey:
    if _inside_repo(path):
        raise refuse("private key не читается из репозитория")
    try:
        raw = path.read_bytes().strip()
        seed = bytes.fromhex(raw.decode("ascii"))
    except Exception as exc:
        raise refuse(f"не прочитать private key {path.name}: {exc}") from exc
    if len(seed) != 32:
        raise refuse("private key должен быть 32 байта hex")
    return Ed25519PrivateKey.from_private_bytes(seed)


def sign_manifest(manifest_bytes: bytes, key: Ed25519PrivateKey) -> str:
    manifest = load_json_bytes(manifest_bytes, "manifest")
    signed = DOMAIN + b"\n" + canonical(manifest)
    return key.sign(signed).hex()


def manifest_command(args: argparse.Namespace) -> int:
    anchor_bytes = Path(args.anchor).read_bytes()
    fingerprint, _public, _min_epoch, _revoked, expected_prev = load_anchor(anchor_bytes)
    prev = args.prev or expected_prev
    if not DIGEST_RE.match(prev):
        raise refuse("--prev должен быть sha256:<lowercase hex>")
    digest_paths = {
        "card_digest": args.card,
        "source_digest": args.source,
        "binary_digest": args.binary,
        "fixture_digest": args.fixture,
        "policy_digest": args.policy,
        "room_digest": args.room,
    }
    manifest = {
        "schema": "herness-admission-v1",
        "kind": "tool_admission",
        "tool": args.tool,
        "key_fingerprint": fingerprint,
        "epoch": args.epoch,
        "seq": args.seq,
        "prev": prev,
        "not_before": args.not_before,
        "not_after": args.not_after,
        "test_only": bool(args.test_only),
    }
    for field, path in digest_paths.items():
        manifest[field] = digest_file(Path(path))
    # Проверяем форму до записи; подпись появится отдельным файлом.
    canonical(manifest)
    output = Path(args.out)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"manifest: {output}")
    print(f"fingerprint: {fingerprint}")
    print(f"test_only: {str(bool(args.test_only)).lower()}")
    return 0


def sign_command(args: argparse.Namespace) -> int:
    key = load_private_key(Path(args.key))
    signature = sign_manifest(Path(args.manifest).read_bytes(), key)
    Path(args.out).write_text(signature + "\n", encoding="ascii")
    public = public_bytes(key)
    print(f"signature: {args.out}")
    print(f"fingerprint: {digest_bytes(public)}")
    return 0


def verify_command(args: argparse.Namespace) -> int:
    now = (
        parse_time(args.now, "--now")
        if args.now
        else int(_datetime.datetime.now(tz=_datetime.timezone.utc).timestamp())
    )
    signature = Path(args.sig).read_text(encoding="ascii")
    result = verify_admission(
        Path(args.manifest).read_bytes(),
        signature,
        Path(args.anchor).read_bytes(),
        now,
        allow_test_only=args.allow_test_only,
    )
    verify_checks(result, args.check)
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def revoke_command(args: argparse.Namespace) -> int:
    if not args.i_am_owner:
        raise refuse("revoke меняет anchor; нужен явный --i-am-owner")
    path = Path(args.anchor)
    anchor = load_json_bytes(path.read_bytes(), "anchor")
    if not isinstance(anchor, dict):
        raise refuse("anchor должен быть объектом")
    revoked = list(anchor.get("revoked_epochs", []))
    if args.epoch not in revoked:
        revoked.append(args.epoch)
    anchor["revoked_epochs"] = sorted(revoked)
    anchor["min_epoch"] = max(int(anchor.get("min_epoch", 0)), args.epoch + 1)
    path.write_text(
        json.dumps(anchor, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"anchor: {path}")
    print(f"revoked_epochs: {anchor['revoked_epochs']}")
    print(f"min_epoch: {anchor['min_epoch']}")
    return 0


def keygen_command(args: argparse.Namespace) -> int:
    if not args.test_only:
        raise refuse("агент создаёт только эфемерные test-only ключи; owner-церемония — вне агента")
    _key_path, anchor_path, fingerprint = create_test_key(Path(args.dir))
    print(f"anchor: {anchor_path}")
    print(f"fingerprint: {fingerprint}")
    print("test_only: true")
    return 0


def _expect_refusal(label: str, callable_, needle: str | None = None) -> None:
    try:
        callable_()
    except AdmissionError as exc:
        if not str(exc).startswith("K11_ADMISSION_REQUIRED:"):
            raise AssertionError(f"{label}: неверный код отказа: {exc}") from exc
        if needle is not None and needle not in str(exc):
            raise AssertionError(f"{label}: в отказе нет {needle!r}: {exc}") from exc
        return
    raise AssertionError(f"{label}: ожидался K11, получен успех")


def self_test() -> int:
    checks = 0
    assert canonical(
        {"b": [True, None, -3, "текст\n"], "a": {"z": 1, "y": "\u001f"}}
    ) == b'{"a":{"y":"\\u001f","z":1},"b":[true,null,-3,"\xd1\x82\xd0\xb5\xd0\xba\xd1\x81\xd1\x82\\n"]}'
    checks += 1
    directory = Path(tempfile.mkdtemp(prefix="herness-admission-selftest-"))
    try:
        key_path, anchor_path, fingerprint = create_test_key(directory / "keys")
        if os.name == "posix":
            assert key_path.stat().st_mode & 0o777 == 0o600
        assert len(fingerprint) == 71 and fingerprint.startswith("sha256:")
        checks += 2

        _expect_refusal(
            "keygen inside repo",
            lambda: create_test_key(ROOT / "core-rs" / "never-test-key"),
        )
        checks += 1

        key = load_private_key(key_path)
        anchor_bytes = anchor_path.read_bytes()
        targets = {}
        for field in DIGEST_FIELDS:
            target = directory / f"{field}.bin"
            target.write_bytes(f"{field}: baseline\n".encode())
            targets[field] = target
        policy_path = directory / "policy.json"
        policy_path.write_bytes(b'{"allow":[],"deny":[]}\n')
        targets["policy_digest"] = policy_path
        room_path = directory / "room.json"
        room_path.write_bytes(b'{"network":false,"write_allowed":false}\n')
        targets["room_digest"] = room_path
        targets["card_digest"].write_bytes(b"card: baseline\n")
        targets["source_digest"].write_bytes(b"source: baseline\n")
        targets["binary_digest"].write_bytes(b"\x7fELF baseline\n")
        targets["fixture_digest"].write_bytes(b"fixture: baseline\n")

        manifest = {
            "schema": "herness-admission-v1",
            "kind": "tool_admission",
            "tool": "head",
            "key_fingerprint": fingerprint,
            "epoch": 1,
            "seq": 1,
            "prev": GENESIS,
            "not_before": "2026-01-01T00:00:00Z",
            "not_after": "2027-01-01T00:00:00Z",
            "test_only": True,
        }
        for field in DIGEST_FIELDS:
            manifest[field] = digest_file(targets[field])
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        signature = sign_manifest(manifest_path.read_bytes(), key)
        signature_path = directory / "manifest.sig"
        signature_path.write_text(signature + "\n", encoding="ascii")
        now = parse_time("2026-06-01T00:00:00Z", "now")
        result = verify_admission(
            manifest_path.read_bytes(), signature, anchor_bytes, now, allow_test_only=True
        )
        assert result["tool"] == "head" and result["signature_ok"] and result["validity_ok"]
        verify_checks(result, [f"{name}={targets[name]}" for name in DIGEST_FIELDS])
        checks += 2

        _expect_refusal(
            "test-only without permission",
            lambda: verify_admission(
                manifest_path.read_bytes(), signature, anchor_bytes, now, allow_test_only=False
            ),
        )
        checks += 1

        original = targets["card_digest"].read_bytes()
        targets["card_digest"].write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        try:
            _expect_refusal(
                "one byte card",
                lambda: verify_checks(
                    result, [f"{name}={targets[name]}" for name in DIGEST_FIELDS]
                ),
            )
        finally:
            targets["card_digest"].write_bytes(original)
        checks += 1

        fixture = targets["fixture_digest"].read_bytes()
        targets["fixture_digest"].write_bytes(fixture[:-1] + bytes([fixture[-1] ^ 0x80]))
        try:
            _expect_refusal(
                "one byte fixture",
                lambda: verify_checks(
                    result, [f"{name}={targets[name]}" for name in DIGEST_FIELDS]
                ),
            )
        finally:
            targets["fixture_digest"].write_bytes(fixture)
        checks += 1

        _expect_refusal(
            "expired",
            lambda: verify_admission(
                manifest_path.read_bytes(),
                signature,
                anchor_bytes,
                parse_time("2028-01-01T00:00:00Z", "now"),
                allow_test_only=True,
            ),
        )
        checks += 1

        revoked = json.loads(anchor_bytes)
        revoked["revoked_epochs"] = [1]
        _expect_refusal(
            "revoked",
            lambda: verify_admission(
                manifest_path.read_bytes(),
                signature,
                canonical(revoked),
                now,
                allow_test_only=True,
            ),
        )
        checks += 1

        revoke_path = directory / "revoke-anchor.json"
        shutil.copyfile(anchor_path, revoke_path)
        _expect_refusal(
            "revoke without owner flag",
            lambda: revoke_command(
                argparse.Namespace(anchor=str(revoke_path), epoch=1, i_am_owner=False)
            ),
        )
        assert revoke_command(
            argparse.Namespace(anchor=str(revoke_path), epoch=1, i_am_owner=True)
        ) == 0
        revoked_anchor = load_json_bytes(revoke_path.read_bytes(), "anchor")
        assert revoked_anchor["min_epoch"] == 2 and revoked_anchor["revoked_epochs"] == [1]
        _expect_refusal(
            "revoke command result",
            lambda: verify_admission(
                manifest_path.read_bytes(),
                signature,
                revoke_path.read_bytes(),
                now,
                allow_test_only=True,
            ),
        )
        checks += 3

        raised = json.loads(anchor_bytes)
        raised["min_epoch"] = 2
        _expect_refusal(
            "min_epoch rollback",
            lambda: verify_admission(
                manifest_path.read_bytes(),
                signature,
                canonical(raised),
                now,
                allow_test_only=True,
            ),
        )
        checks += 1

        other_key = Ed25519PrivateKey.from_private_bytes(b"\x09" * 32)
        other_public = public_bytes(other_key)
        wrong_anchor = {
            "schema": "herness-anchor-v1",
            "kind": "owner_anchor",
            "public_key": other_public.hex(),
            "key_fingerprint": digest_bytes(other_public),
            "min_epoch": 1,
            "revoked_epochs": [],
            "expected_prev": GENESIS,
        }
        _expect_refusal(
            "wrong anchor",
            lambda: verify_admission(
                manifest_path.read_bytes(),
                signature,
                canonical(wrong_anchor),
                now,
                allow_test_only=True,
            ),
        )
        checks += 1

        bad_sig = ("00" if signature[:2] != "00" else "01") + signature[2:]
        _expect_refusal(
            "tampered signature",
            lambda: verify_admission(
                manifest_path.read_bytes(), bad_sig, anchor_bytes, now, allow_test_only=True
            ),
        )
        checks += 1

        broken_prev = dict(manifest)
        broken_prev["prev"] = digest_bytes(b"other chain")
        broken_manifest = canonical(broken_prev)
        broken_signature = key.sign(DOMAIN + b"\n" + broken_manifest).hex()
        _expect_refusal(
            "wrong prev",
            lambda: verify_admission(
                broken_manifest, broken_signature, anchor_bytes, now, allow_test_only=True
            ),
        )
        checks += 1

        for label, manifest_arg, sig_arg, anchor_arg in (
            ("missing signature", manifest_path.read_bytes(), "", anchor_bytes),
            ("missing anchor", manifest_path.read_bytes(), signature, b"{}"),
            ("missing manifest", b"{}", signature, anchor_bytes),
        ):
            _expect_refusal(
                label,
                lambda manifest_arg=manifest_arg, sig_arg=sig_arg, anchor_arg=anchor_arg: verify_admission(
                    manifest_arg, sig_arg, anchor_arg, now, allow_test_only=True
                ),
            )
            checks += 1

        # Подпись покрывает точные канонические байты, а не pretty-файл:
        pretty = json.dumps(manifest, ensure_ascii=False, indent=4, sort_keys=True) + "\n"
        verify_admission(pretty.encode(), signature, anchor_bytes, now, allow_test_only=True)
        checks += 1

        # Float запрещён и в манифесте, и в anchor.
        _expect_refusal(
            "float manifest",
            lambda: verify_admission(
                b'{"schema":"herness-admission-v1","x":1.5}', signature, anchor_bytes, now, True
            ),
        )
        checks += 1

        # Повтор ключа: два парсера не должны читать подписанный файл по-разному.
        duplicate_manifest = canonical(manifest)[:-1] + b',"test_only":true}'
        _expect_refusal(
            "duplicate manifest key",
            lambda: verify_admission(
                duplicate_manifest, signature, anchor_bytes, now, allow_test_only=True
            ),
            "повтор ключа",
        )
        checks += 1

        duplicate_anchor = canonical(json.loads(anchor_bytes))[:-1] + b',"min_epoch":1}'
        _expect_refusal(
            "duplicate anchor key",
            lambda: verify_admission(
                manifest_path.read_bytes(), signature, duplicate_anchor, now, allow_test_only=True
            ),
            "повтор ключа",
        )
        checks += 1

        # JCS-числа — IEEE-754: за пределами ±(2^53-1) парсеры расходятся.
        _expect_refusal(
            "big int canonical",
            lambda: canonical({"seq": 2**53}),
            "безопасного диапазона",
        )
        assert canonical({"seq": SAFE_INT}) == b'{"seq":9007199254740991}'
        big_manifest = dict(manifest)
        big_manifest["seq"] = 2**53 + 1
        big_raw = json.dumps(big_manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
        _expect_refusal(
            "big int manifest",
            lambda: verify_admission(big_raw, signature, anchor_bytes, now, allow_test_only=True),
            "безопасного диапазона",
        )
        checks += 2

        print(f"PASS admission self-test: {checks} проверок")
        print(f"fingerprint: {fingerprint}")
        print("test_only: true; инструмент active не становится")
        return 0
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="admission v0: manifest/sign/verify/revoke")
    sub = parser.add_subparsers(dest="command", required=True)

    keygen = sub.add_parser("keygen", help="создать эфемерный test-only ключ вне репозитория")
    keygen.add_argument("--dir", required=True)
    keygen.add_argument("--test-only", action="store_true", required=True)
    keygen.set_defaults(func=keygen_command)

    manifest = sub.add_parser("manifest", help="собрать манифест из точных файлов")
    manifest.add_argument("--tool", required=True)
    for field in ("card", "source", "binary", "fixture", "policy", "room"):
        manifest.add_argument(f"--{field}", required=True)
    manifest.add_argument("--anchor", required=True)
    manifest.add_argument("--epoch", type=int, default=1)
    manifest.add_argument("--seq", type=int, default=1)
    manifest.add_argument("--prev")
    manifest.add_argument("--not-before", default="2026-11-17T00:00:00Z")
    manifest.add_argument("--not-after", default="2027-11-17T00:00:00Z")
    manifest.add_argument("--test-only", action="store_true")
    manifest.add_argument("--out", required=True)
    manifest.set_defaults(func=manifest_command)

    sign = sub.add_parser("sign", help="detached Ed25519 по каноническим байтам")
    sign.add_argument("--manifest", required=True)
    sign.add_argument("--key", required=True)
    sign.add_argument("--out", required=True)
    sign.set_defaults(func=sign_command)

    verify = sub.add_parser("verify", help="проверить подпись, срок, epoch и точные файлы")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--sig", required=True)
    verify.add_argument("--anchor", required=True)
    verify.add_argument("--now")
    verify.add_argument("--allow-test-only", action="store_true")
    verify.add_argument("--check", action="append", default=[])
    verify.add_argument("--quiet", action="store_true")
    verify.set_defaults(func=verify_command)

    revoke = sub.add_parser("revoke", help="отозвать epoch и поднять min_epoch")
    revoke.add_argument("--anchor", required=True)
    revoke.add_argument("--epoch", type=int, required=True)
    revoke.add_argument("--i-am-owner", action="store_true")
    revoke.set_defaults(func=revoke_command)

    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        return self_test()
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "self_test", False):
        return self_test()
    try:
        return args.func(args)
    except AdmissionError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
