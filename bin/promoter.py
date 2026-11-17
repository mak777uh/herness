"""Promoter v0: проверка admission и запуск только по точным байтам.

Правила:
- на входе — манифест, detached подпись, anchor и шесть exact-byte файлов;
- полная семантика карточки — здесь, в runtime остаётся тонкая проверка;
- Linux: запуск только из memfd с `F_SEAL_*` через `execveat(AT_EMPTY_PATH)`;
  пути к файлу как источнику запуска нет, поэтому подмена байтов после проверки
  не меняет исполняемое;
- Windows/не-Linux: только verify/store, запуск отказом;
- `seal`/`netprobe` вне v0; test-only никогда не активирует инструмент.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import platform
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # Windows: запуск всё равно запрещён, verify работает
    fcntl = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission  # noqa: E402

V0_TOOLS = {"head"}
OUT_OF_V0 = {"seal", "netprobe"}
AT_EMPTY_PATH = 0x1000


class PromoterError(Exception):
    pass


def refuse(reason: str) -> "PromoterError":
    return PromoterError(f"PROMOTER_REFUSED: {reason}")


def now_unix() -> int:
    return int(time.time())


def verify_all(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = Path(args.manifest)
    signature = Path(args.sig).read_text(encoding="ascii")
    now = admission.parse_time(args.now, "--now") if args.now else now_unix()
    result = admission.verify_admission(
        manifest_path.read_bytes(),
        signature,
        Path(args.anchor).read_bytes(),
        now,
        allow_test_only=args.allow_test_only,
    )
    checks = [
        f"card_digest={args.card}",
        f"source_digest={args.source}",
        f"binary_digest={args.binary}",
        f"fixture_digest={args.fixture}",
        f"policy_digest={args.policy}",
        f"room_digest={args.room}",
    ]
    admission.verify_checks(result, checks)
    result["checks"] = {item.split("=", 1)[0]: str(Path(item.split("=", 1)[1]).resolve()) for item in checks}
    result["checked_at_unix"] = now
    return result


def store(result: dict[str, Any], args: argparse.Namespace) -> Path:
    directory = Path(args.store)
    directory.mkdir(parents=True, exist_ok=True)
    for name, source in (
        ("manifest.json", args.manifest),
        ("manifest.sig", args.sig),
        ("anchor.json", args.anchor),
        ("binary", args.binary),
    ):
        target = directory / name
        shutil.copyfile(source, target)
    summary = {
        key: result[key]
        for key in (
            "schema",
            "kind",
            "tool",
            "epoch",
            "seq",
            "test_only",
            "key_fingerprint",
            "digests",
            "signature_ok",
            "validity_ok",
            "checked_at_unix",
        )
    }
    summary["stored_at"] = str(directory)
    (directory / "promotion.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return directory


def summary(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)


def verify_command(args: argparse.Namespace) -> int:
    result = verify_all(args)
    if args.store:
        store(result, args)
    if not args.quiet:
        print(summary(result))
    return 0


def _execveat(fd: int, argv: list[str]) -> None:
    """Заменяет процесс через execveat(fd, "", ..., AT_EMPTY_PATH).

    Возврата при успехе нет. Любая ошибка — отказ: fallback на путь запрещён,
    иначе exact-byte проверка теряет смысл.
    """
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        syscall_number = 322
    elif machine in ("aarch64", "arm64"):
        syscall_number = 281
    else:
        raise refuse(f"execveat не поддержан для архитектуры {machine}")
    libc = ctypes.CDLL(None, use_errno=True)
    encoded = [arg.encode("utf-8") for arg in argv]
    argv_array = (ctypes.c_char_p * (len(encoded) + 1))(*encoded, None)
    env = [f"{key}={value}".encode("utf-8") for key, value in os.environ.items()]
    env_array = (ctypes.c_char_p * (len(env) + 1))(*env, None)
    libc.syscall.restype = ctypes.c_long
    result = libc.syscall(
        ctypes.c_long(syscall_number),
        ctypes.c_int(fd),
        ctypes.c_char_p(b""),
        ctypes.cast(argv_array, ctypes.c_void_p),
        ctypes.cast(env_array, ctypes.c_void_p),
        ctypes.c_int(AT_EMPTY_PATH),
    )
    error = ctypes.get_errno()
    raise refuse(f"execveat вернул {result}, errno={error} ({errno.errorcode.get(error, '?')})")


def promote_command(args: argparse.Namespace) -> int:
    result = verify_all(args)
    tool = result["tool"]
    if tool in OUT_OF_V0:
        raise refuse(f"{tool} вне v0: допускается только head")
    if tool not in V0_TOOLS:
        raise refuse(f"инструмент {tool} не входит в v0 promoter")
    if args.store:
        store(result, args)
    if not sys.platform.startswith("linux"):
        raise refuse(
            "запуск по exact bytes возможен только на Linux (memfd + execveat); "
            "проверка выполнена, инструмент не активирован"
        )
    binary = Path(args.binary)
    try:
        payload = binary.read_bytes()
    except OSError as exc:
        raise refuse(f"не прочитать binary {binary}: {exc}") from exc
    if admission.digest_bytes(payload) != result["digests"]["binary_digest"]:
        raise refuse("binary изменился между проверкой и запуском")
    if not hasattr(os, "memfd_create"):
        raise refuse("в этой сборке Python нет os.memfd_create")
    memfd = os.memfd_create("herness-promoter", os.MFD_ALLOW_SEALING)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(memfd, view)
            if written <= 0:
                raise refuse("memfd: запись не продвинулась")
            view = view[written:]
        os.fchmod(memfd, 0o700)
        if fcntl is None:
            raise refuse("модуль fcntl недоступен: F_SEAL невозможен")
        seals = (
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE
        )
        fcntl.fcntl(memfd, fcntl.F_ADD_SEALS, seals)
    except OSError as exc:
        os.close(memfd)
        raise refuse(f"memfd/F_SEAL не удались: {exc}") from exc
    argv = [str(binary), *args.arg]
    if not args.quiet:
        print(
            json.dumps(
                {
                    "launch": "execveat-memfd",
                    "tool": tool,
                    "test_only": result["test_only"],
                    "key_fingerprint": result["key_fingerprint"],
                    "activation": "none: promoter не меняет registry",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        sys.stdout.flush()
    _execveat(memfd, argv)
    return 0


def _run_promoter(args: list[str]) -> Any:
    import subprocess

    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
    )


def self_test() -> int:
    checks = 0
    directory = Path(tempfile.mkdtemp(prefix="herness-promoter-selftest-"))
    try:
        key_path, anchor_path, fingerprint = admission.create_test_key(directory / "keys")
        key = admission.load_private_key(key_path)
        anchor_bytes = anchor_path.read_bytes()
        targets = {
            "card": directory / "card.json",
            "source": directory / "head.rs",
            "binary": directory / "head.bin",
            "fixture": directory / "fixture.txt",
            "policy": directory / "policy.json",
            "room": directory / "room.json",
        }
        targets["card"].write_bytes(b'{"id":"head","schema_version":"tool-card-v1"}\n')
        targets["source"].write_bytes(b"fn head() {}\n")
        true_binary = shutil.which("true") if sys.platform.startswith("linux") else None
        if true_binary:
            # На Linux запускаем настоящий ELF, чтобы проверить memfd+execveat.
            shutil.copyfile(true_binary, targets["binary"])
        else:
            targets["binary"].write_bytes(b"\x7fELF baseline\n")
        targets["fixture"].write_bytes(b"synthetic model_visible\n")
        targets["policy"].write_bytes(b'{"allow":["file:/mnt/fixtures/**"],"deny":[]}\n')
        targets["room"].write_bytes(b'{"network":false,"disk":false,"write_allowed":false}\n')
        manifest = {
            "schema": "herness-admission-v1",
            "kind": "tool_admission",
            "tool": "head",
            "key_fingerprint": fingerprint,
            "epoch": 1,
            "seq": 1,
            "prev": admission.GENESIS,
            "not_before": "2026-01-01T00:00:00Z",
            "not_after": "2027-01-01T00:00:00Z",
            "test_only": True,
        }
        for field, name in (
            ("card_digest", "card"),
            ("source_digest", "source"),
            ("binary_digest", "binary"),
            ("fixture_digest", "fixture"),
            ("policy_digest", "policy"),
            ("room_digest", "room"),
        ):
            manifest[field] = admission.digest_file(targets[name])
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        signature = admission.sign_manifest(manifest_path.read_bytes(), key)
        sig_path = directory / "manifest.sig"
        sig_path.write_text(signature + "\n", encoding="ascii")

        base = [
            "--manifest", str(manifest_path),
            "--sig", str(sig_path),
            "--anchor", str(anchor_path),
            "--card", str(targets["card"]),
            "--source", str(targets["source"]),
            "--binary", str(targets["binary"]),
            "--fixture", str(targets["fixture"]),
            "--policy", str(targets["policy"]),
            "--room", str(targets["room"]),
        ]
        common = [*base, "--now", "2026-06-01T00:00:00Z", "--allow-test-only"]
        verify = _run_promoter(["verify", *common, "--quiet"])
        assert verify.returncode == 0, (verify.returncode, verify.stdout, verify.stderr)
        checks += 1

        no_permission = [item for item in common if item != "--allow-test-only"]
        refused = _run_promoter(["verify", *no_permission, "--quiet"])
        assert refused.returncode != 0 and "K11_ADMISSION_REQUIRED" in refused.stderr
        checks += 1

        original = targets["binary"].read_bytes()
        targets["binary"].write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        try:
            refused = _run_promoter(["verify", *common, "--quiet"])
            assert refused.returncode != 0 and "K11_ADMISSION_REQUIRED" in refused.stderr
            checks += 1
        finally:
            targets["binary"].write_bytes(original)

        if sys.platform.startswith("linux"):
            result = _run_promoter(["promote", *common, "--arg", "0"])
            assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
            checks += 1
            print("PASS promoter self-test: Linux launch через memfd+execveat")
        else:
            result = _run_promoter(["promote", *common])
            assert result.returncode != 0
            assert "PROMOTER_REFUSED" in result.stderr and "Linux" in result.stderr
            checks += 1
            print("PASS promoter self-test: Windows verify/store, запуск отказом (N/A для launch)")

        # store работает и не содержит private seed
        stored = directory / "store"
        result = _run_promoter(["verify", *common, "--store", str(stored), "--quiet"])
        assert result.returncode == 0, (result.returncode, result.stderr)
        names = {item.name for item in stored.iterdir()}
        assert {"manifest.json", "manifest.sig", "anchor.json", "binary", "promotion.json"} <= names
        assert not any("seed" in name for name in names)
        checks += 1

        # seal/netprobe вне v0 — отказ до запуска
        seal_manifest = dict(manifest)
        seal_manifest["tool"] = "seal"
        seal_bytes = admission.canonical(seal_manifest)
        seal_signature = key.sign(admission.DOMAIN + b"\n" + seal_bytes).hex()
        (directory / "seal.json").write_bytes(seal_bytes)
        (directory / "seal.sig").write_text(seal_signature + "\n", encoding="ascii")
        seal_args = [item for item in common]
        seal_args[seal_args.index(str(manifest_path))] = str(directory / "seal.json")
        seal_args[seal_args.index(str(sig_path))] = str(directory / "seal.sig")
        result = _run_promoter(["promote", *seal_args])
        assert result.returncode != 0 and "вне v0" in result.stderr, (
            result.returncode,
            result.stdout,
            result.stderr,
        )
        checks += 1

        # Просроченный admission: подпись верна, срок нет.
        expired = _run_promoter(
            ["verify", *base, "--now", "2028-01-01T00:00:00Z", "--allow-test-only", "--quiet"]
        )
        assert expired.returncode != 0 and "просрочен" in expired.stderr
        checks += 1

        # Отозванный epoch: anchor меняется, подпись та же.
        revoked = json.loads(anchor_bytes)
        revoked["revoked_epochs"] = [1]
        revoked_path = directory / "revoked-anchor.json"
        revoked_path.write_bytes(admission.canonical(revoked))
        revoked_args = list(common)
        revoked_args[revoked_args.index(str(anchor_path))] = str(revoked_path)
        result = _run_promoter(["verify", *revoked_args, "--quiet"])
        assert result.returncode != 0 and "отозван" in result.stderr
        checks += 1

        # Неверный anchor.
        other = admission.Ed25519PrivateKey.from_private_bytes(b"\x0a" * 32)
        other_public = admission.public_bytes(other)
        wrong = {
            "schema": "herness-anchor-v1",
            "kind": "owner_anchor",
            "public_key": other_public.hex(),
            "key_fingerprint": admission.digest_bytes(other_public),
            "min_epoch": 1,
            "revoked_epochs": [],
            "expected_prev": admission.GENESIS,
        }
        wrong_path = directory / "wrong-anchor.json"
        wrong_path.write_bytes(admission.canonical(wrong))
        wrong_args = list(common)
        wrong_args[wrong_args.index(str(anchor_path))] = str(wrong_path)
        result = _run_promoter(["verify", *wrong_args, "--quiet"])
        assert result.returncode != 0 and "K11_ADMISSION_REQUIRED" in result.stderr
        checks += 1

        print(f"PASS promoter self-test: {checks} проверок")
        print(f"fingerprint: {fingerprint}")
        return 0
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="promoter v0: verify и exact-byte launch")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--manifest", required=True)
        subparser.add_argument("--sig", required=True)
        subparser.add_argument("--anchor", required=True)
        subparser.add_argument("--card", required=True)
        subparser.add_argument("--source", required=True)
        subparser.add_argument("--binary", required=True)
        subparser.add_argument("--fixture", required=True)
        subparser.add_argument("--policy", required=True)
        subparser.add_argument("--room", required=True)
        subparser.add_argument("--now")
        subparser.add_argument("--allow-test-only", action="store_true")
        subparser.add_argument("--store")
        subparser.add_argument("--quiet", action="store_true")

    verify = sub.add_parser("verify", help="проверить все шесть digest и подпись")
    common(verify)
    verify.set_defaults(func=verify_command)

    promote = sub.add_parser("promote", help="проверить и запустить exact bytes (Linux)")
    common(promote)
    promote.add_argument("--arg", action="append", default=[])
    promote.set_defaults(func=promote_command)

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
    except (admission.AdmissionError, PromoterError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
