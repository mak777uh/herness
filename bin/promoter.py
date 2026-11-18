"""Promoter v0: проверка admission и запуск только по точным байтам.

Правила:
- на входе — манифест, detached подпись, anchor и шесть exact-byte файлов;
- v0 проверяет схему/id карточки и точные digest; полная семантика
  preconditions/postconditions ещё не реализована — это известный разрыв;
- Linux: запуск только из memfd с `F_SEAL_*` через `execveat(AT_EMPTY_PATH)`;
  пути к файлу как источнику запуска нет, поэтому подмена байтов после проверки
  не меняет исполняемое;
- для `head` запуск требует `--job` (или `--arg=--job PATH`): root, fixture
  manifest, checks и admission внутри job обязаны совпадать с проверенными
  путями; per-case override запрещён. Точные байты job тоже запечатаны в memfd
  и передаются хосту унаследованным fd (`--job-fd`), поэтому подмена файла job
  между проверкой и запуском не проходит;
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
CHECK_ARGS = {
    "card_digest": "card",
    "source_digest": "source",
    "binary_digest": "binary",
    "fixture_digest": "fixture",
    "policy_digest": "policy",
    "room_digest": "room",
}
ADMISSION_ARGS = {"manifest": "manifest", "sig": "sig", "anchor": "anchor"}
JOB_KEYS = {"root", "now_unix", "fixture_manifest", "admission", "checks", "cases"}


class PromoterError(Exception):
    pass


def refuse(reason: str) -> "PromoterError":
    return PromoterError(f"PROMOTER_REFUSED: {reason}")


def now_unix() -> int:
    return int(time.time())


def _text_field(mapping: dict[str, Any], key: str, what: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise refuse(f"{what}: поле {key} должно быть непустой строкой")
    return value


def _resolved(value: str | Path, what: str) -> Path:
    try:
        return Path(value).resolve(strict=True)
    except OSError as exc:
        raise refuse(f"{what}: путь не разрешается: {value}: {exc}") from exc


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _job_reference(args: argparse.Namespace) -> Path | None:
    """Возвращает job из `--job` или `--arg=--job[=]PATH`, запрещая дубли."""
    found: list[Path] = []
    direct = getattr(args, "job", None)
    if direct:
        if isinstance(direct, list):
            found.extend(Path(item) for item in direct)
        else:
            found.append(Path(direct))
    arguments = list(getattr(args, "arg", []) or [])
    index = 0
    while index < len(arguments):
        item = arguments[index]
        if item == "--job":
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
                raise refuse("--arg=--job без значения")
            found.append(Path(arguments[index + 1]))
            index += 2
            continue
        if item.startswith("--job="):
            value = item.split("=", 1)[1]
            if not value:
                raise refuse("--arg=--job= без значения")
            found.append(Path(value))
        index += 1
    if len(found) > 1:
        raise refuse("job задан более одного раза; неоднозначность запрещена")
    return found[0] if found else None


def _safe_fixture_segment(value: str) -> bool:
    return (
        bool(value)
        and value not in (".", "..")
        and "/" not in value
        and "\\" not in value
        and "\0" not in value
    )


def bind_job(args: argparse.Namespace, result: dict[str, Any]) -> dict[str, Any] | None:
    """Связывает job с уже проверенными путями и admission.

    Это не доверенная конфигурация: job читается как данные, каждое поле
    сверяется с CLI-путями, прошедшими digest-проверку. Per-case override
    запрещён, иначе кейс мог бы отключить admission или подменить fixture
    внутри одного запуска.
    """
    reference = _job_reference(args)
    if reference is None:
        return None
    if result["tool"] != "head":
        raise refuse(f"job поддержан только для head, не для {result['tool']}")
    for item in getattr(args, "arg", []) or []:
        if item == "--job-fd" or item.startswith("--job-fd="):
            raise refuse("--job-fd зарезервирован promoter: job передаётся через --job")
    job_path = _resolved(reference, "job")
    try:
        job_bytes = job_path.read_bytes()
    except OSError as exc:
        raise refuse(f"job: не прочитать {job_path}: {exc}") from exc
    job = admission.load_json_bytes(job_bytes, "job")
    if not isinstance(job, dict):
        raise refuse("job: ожидался объект")
    missing = JOB_KEYS - set(job)
    extra = set(job) - JOB_KEYS
    if missing or extra:
        raise refuse(f"job: состав полей не v0; нет {sorted(missing)}, лишние {sorted(extra)}")

    root = _resolved(_text_field(job, "root", "job"), "job.root")
    if not root.is_dir():
        raise refuse(f"job.root не каталог: {root}")
    now_value = job.get("now_unix")
    if isinstance(now_value, bool) or not isinstance(now_value, int):
        raise refuse("job.now_unix: ожидалось целое")

    fixture_path = _resolved(
        _text_field(job, "fixture_manifest", "job"), "job.fixture_manifest"
    )
    if not _same_path(fixture_path, Path(result["checks"]["fixture_digest"])):
        raise refuse("job.fixture_manifest не совпадает с проверенным --fixture")

    checks = job.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(CHECK_ARGS):
        raise refuse("job.checks: ожидались ровно шесть digest-путей")
    for field in CHECK_ARGS:
        value = _resolved(_text_field(checks, field, "job.checks"), f"job.checks.{field}")
        if not _same_path(value, Path(result["checks"][field])):
            raise refuse(f"job.checks.{field} не совпадает с проверенным путём")

    job_admission = job.get("admission")
    if not isinstance(job_admission, dict) or set(job_admission) != set(ADMISSION_ARGS):
        raise refuse("job.admission: ожидались manifest, sig и anchor")
    for key, attribute in ADMISSION_ARGS.items():
        value = _resolved(
            _text_field(job_admission, key, "job.admission"), f"job.admission.{key}"
        )
        cli_path = _resolved(getattr(args, attribute), f"--{attribute}")
        if not _same_path(value, cli_path):
            raise refuse(f"job.admission.{key} не совпадает с проверенным --{attribute}")

    try:
        fixture_bytes = fixture_path.read_bytes()
    except OSError as exc:
        raise refuse(f"job.fixture_manifest: не прочитать {fixture_path}: {exc}") from exc
    fixture = admission.load_json_bytes(fixture_bytes, "job.fixture_manifest")
    if not isinstance(fixture, dict):
        raise refuse("job.fixture_manifest: ожидался объект")
    if fixture.get("schema_version") != "fixture-manifest-v1":
        raise refuse("job.fixture_manifest: ожидалась схема fixture-manifest-v1")
    root_ref = fixture.get("root_ref")
    if not isinstance(root_ref, str) or not root_ref:
        raise refuse("job.fixture_manifest: root_ref должен быть непустой строкой")
    fixture_root = fixture.get("fixture_root")
    if not isinstance(fixture_root, str) or not _safe_fixture_segment(fixture_root):
        raise refuse("job.fixture_manifest: fixture_root должен быть безопасным сегментом")
    try:
        fixture_parent = fixture_path.parent.resolve(strict=True)
        expected_parent = (root / fixture_root).resolve(strict=True)
    except OSError as exc:
        raise refuse(f"job.root/fixture_root не разрешается: {exc}") from exc
    if not _same_path(fixture_parent, expected_parent):
        raise refuse(
            "job.root не соответствует расположению fixture manifest: "
            f"{fixture_parent} != {expected_parent}"
        )

    cases = job.get("cases")
    if not isinstance(cases, list) or not cases:
        raise refuse("job.cases: ожидался непустой массив")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise refuse(f"job.cases[{index}]: ожидался объект")
        overrides = [
            key for key in ("admission", "checks", "fixture_manifest") if key in case
        ]
        if overrides:
            raise refuse(
                f"job.cases[{index}] переопределяет {', '.join(overrides)}; "
                "promoter v0 запрещает per-case override"
            )

    result["_job_bytes"] = job_bytes
    result["exact_bytes"]["job"] = admission.digest_bytes(job_bytes)
    return {
        "path": str(job_path),
        "sha256": admission.digest_bytes(job_bytes),
        "root": str(root),
        "fixture_manifest": str(fixture_path),
        "fixture_root": fixture_root,
        "root_ref": root_ref,
        "cases": len(cases),
    }


def verify_all(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = Path(args.manifest)
    manifest_bytes = manifest_path.read_bytes()
    signature_bytes = Path(args.sig).read_bytes()
    anchor_bytes = Path(args.anchor).read_bytes()
    try:
        signature = signature_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise refuse(f"подпись не ASCII: {exc}") from exc
    now = admission.parse_time(args.now, "--now") if args.now else now_unix()
    result = admission.verify_admission(
        manifest_bytes,
        signature,
        anchor_bytes,
        now,
        allow_test_only=args.allow_test_only,
    )
    card = admission.load_json_bytes(Path(args.card).read_bytes(), "card")
    if not isinstance(card, dict) or card.get("schema_version") != "tool-card-v1":
        raise refuse("card: ожидалась схема tool-card-v1")
    if card.get("id") != result["tool"]:
        raise refuse(
            f"card: id {card.get('id')!r} не совпадает с tool {result['tool']!r}"
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
    # Точные байты, которые прошли проверку. store обязан записать именно их,
    # а не перечитать путь: иначе между verify и записью возможна подмена.
    result["exact_bytes"] = {
        "manifest": admission.digest_bytes(manifest_bytes),
        "signature": admission.digest_bytes(signature_bytes),
        "anchor": admission.digest_bytes(anchor_bytes),
    }
    result["job"] = bind_job(args, result)
    return result


def _read_exact(path: str, expected: str, what: str) -> bytes:
    data = Path(path).read_bytes()
    actual = admission.digest_bytes(data)
    if actual != expected:
        raise refuse(f"{what} изменился после проверки: ожидалось {expected}, получено {actual}")
    return data


def store(result: dict[str, Any], args: argparse.Namespace) -> Path:
    directory = Path(args.store)
    # Сначала читаем и сверяем все байты, только потом создаём каталог.
    # Частично записанный store не должен выглядеть как доказательство.
    exact = {
        "manifest.json": _read_exact(
            args.manifest, result["exact_bytes"]["manifest"], "manifest"
        ),
        "manifest.sig": _read_exact(args.sig, result["exact_bytes"]["signature"], "signature"),
        "anchor.json": _read_exact(args.anchor, result["exact_bytes"]["anchor"], "anchor"),
        "binary": _read_exact(args.binary, result["digests"]["binary_digest"], "binary"),
    }
    if result.get("job"):
        # job проверен и запечатан вместе с binary; store хранит именно его
        # байты, иначе evidence описывает не тот запуск.
        exact["job.json"] = result["_job_bytes"]
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
            "exact_bytes",
            "job",
        )
        if key in result
    }
    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".store-staging-", dir=directory.parent))
    try:
        for name, data in exact.items():
            (staging / name).write_bytes(data)
        (staging / "promotion.json").write_text(
            json.dumps(
                {**summary, "stored_at": str(directory)}, ensure_ascii=False, indent=2, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        directory.mkdir(parents=True, exist_ok=True)
        for name in exact:
            os.replace(staging / name, directory / name)
        os.replace(staging / "promotion.json", directory / "promotion.json")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return directory


def summary(result: dict[str, Any]) -> str:
    public = {key: value for key, value in result.items() if not key.startswith("_")}
    return json.dumps(public, ensure_ascii=False, indent=2, sort_keys=True)


def verify_command(args: argparse.Namespace) -> int:
    result = verify_all(args)
    if args.store:
        store(result, args)
    if not args.quiet:
        print(summary(result))
    return 0


def _sealed_memfd(name: str, payload: bytes, cloexec: bool) -> int:
    if not hasattr(os, "memfd_create"):
        raise refuse("в этой сборке Python нет os.memfd_create")
    flags = os.MFD_ALLOW_SEALING | (os.MFD_CLOEXEC if cloexec else 0)
    memfd = os.memfd_create(name, flags)
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
    except BaseException:
        os.close(memfd)
        raise
    return memfd


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
    # Окружение хоста не объявлено в комнате и может содержать секреты.
    # Дочерний процесс получает пустое окружение, а не копию родительского.
    env: list[bytes] = []
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


def _argv_with_job(args: argparse.Namespace, job_fd: int) -> list[str]:
    """Убирает путь job из argv и передаёт унаследованный fd запечатанного memfd."""
    forwarded: list[str] = []
    found = 0
    arguments = list(args.arg)
    index = 0
    while index < len(arguments):
        item = arguments[index]
        if item == "--job":
            found += 1
            index += 2
            continue
        if item.startswith("--job="):
            found += 1
            index += 1
            continue
        forwarded.append(item)
        index += 1
    direct = getattr(args, "job", None)
    if direct:
        found += len(direct) if isinstance(direct, list) else 1
    if found != 1:
        raise refuse(f"job: ожидался ровно один источник, найдено {found}")
    forwarded.extend(["--job-fd", str(job_fd)])
    return forwarded


def promote_command(args: argparse.Namespace) -> int:
    result = verify_all(args)
    tool = result["tool"]
    if tool in OUT_OF_V0:
        raise refuse(f"{tool} вне v0: допускается только head")
    if tool not in V0_TOOLS:
        raise refuse(f"инструмент {tool} не входит в v0 promoter")
    if result.get("job") is None:
        raise refuse(
            "head promote требует --job: без него root/fixture/checks не связаны "
            "с подписанным admission"
        )
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
    # job не перечитывается из пути: хост получает запечатанный memfd.
    # Иначе подмена файла между bind_job и стартом обошла бы привязку.
    job_memfd = _sealed_memfd("herness-job", result["_job_bytes"], cloexec=False)
    try:
        memfd = _sealed_memfd("herness-promoter", payload, cloexec=True)
    except BaseException:
        os.close(job_memfd)
        raise
    argv = [str(binary), *_argv_with_job(args, job_memfd)]
    if not args.quiet:
        print(
            json.dumps(
                {
                    "launch": "execveat-memfd",
                    "tool": tool,
                    "test_only": result["test_only"],
                    "key_fingerprint": result["key_fingerprint"],
                    "job_sha256": result["job"]["sha256"],
                    "job_transport": "memfd:fd",
                    "activation": "none: promoter не меняет registry",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        sys.stdout.flush()
    _execveat(memfd, argv)
    return 0


def _run_promoter(args: list[str], env: dict[str, str] | None = None) -> Any:
    import subprocess

    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
        env=env,
    )


def self_test() -> int:
    checks = 0
    directory = Path(tempfile.mkdtemp(prefix="herness-promoter-selftest-"))
    try:
        key_path, anchor_path, fingerprint = admission.create_test_key(directory / "keys")
        key = admission.load_private_key(key_path)
        anchor_bytes = anchor_path.read_bytes()
        room = directory / "room"
        fixtures = room / "fixtures"
        fixtures.mkdir(parents=True)
        targets = {
            "card": directory / "card.json",
            "source": directory / "head.rs",
            "binary": directory / "head.bin",
            "fixture": fixtures / "manifest.json",
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
        fixture_bytes = b"synthetic model_visible\n"
        (fixtures / "data.txt").write_bytes(fixture_bytes)
        fixture_manifest = {
            "schema_version": "fixture-manifest-v1",
            "root_ref": "room:input",
            "fixture_root": "fixtures",
            "accepted_classes": ["model_visible"],
            "files": [
                {
                    "path": "data.txt",
                    "bytes": len(fixture_bytes),
                    "lines": 1,
                    "sha256": admission.digest_bytes(fixture_bytes),
                    "data_class": "model_visible",
                }
            ],
        }
        targets["fixture"].write_bytes(admission.canonical(fixture_manifest) + b"\n")
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

        def write_job(
            name: str,
            *,
            job_manifest: Path = manifest_path,
            job_sig: Path = sig_path,
            job_binary: Path = targets["binary"],
            job_root: Path = room,
            job_fixture: Path = targets["fixture"],
            job_anchor: Path = anchor_path,
            check_overrides: dict[str, Path] | None = None,
            cases_override: list[dict[str, Any]] | None = None,
        ) -> Path:
            job_checks = {
                "card_digest": targets["card"],
                "source_digest": targets["source"],
                "binary_digest": job_binary,
                "fixture_digest": job_fixture,
                "policy_digest": targets["policy"],
                "room_digest": targets["room"],
            }
            if check_overrides:
                job_checks.update(check_overrides)
            cases = cases_override or [
                {
                    "id": "normal",
                    "path_ref": {
                        "root_ref": "room:input",
                        "segments": ["fixtures", "data.txt"],
                    },
                    "line_count": 1,
                    "max_bytes_read": 32,
                }
            ]
            job = {
                "root": str(job_root),
                "now_unix": 1780272000,
                "fixture_manifest": str(job_fixture),
                "admission": {
                    "manifest": str(job_manifest),
                    "sig": str(job_sig),
                    "anchor": str(job_anchor),
                },
                "checks": {key: str(value) for key, value in job_checks.items()},
                "cases": cases,
            }
            path = directory / f"{name}-job.json"
            path.write_text(
                json.dumps(job, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return path

        base_job = write_job("base")
        base_without_job = [
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
        base = [*base_without_job, "--job", str(base_job)]
        common = [*base, "--now", "2026-06-01T00:00:00Z", "--allow-test-only"]
        no_job_common = [
            *base_without_job,
            "--now", "2026-06-01T00:00:00Z", "--allow-test-only",
        ]

        def variant(binary_path: Path, name: str) -> list[str]:
            """Манифест с другим binary: для проверок env/fd изоляции."""
            value = dict(manifest)
            value["binary_digest"] = admission.digest_file(binary_path)
            manifest_variant = directory / f"{name}-manifest.json"
            manifest_variant.write_text(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            sig_variant = directory / f"{name}.sig"
            sig_variant.write_text(
                admission.sign_manifest(manifest_variant.read_bytes(), key) + "\n",
                encoding="ascii",
            )
            args = list(base_without_job)
            args[args.index(str(manifest_path))] = str(manifest_variant)
            args[args.index(str(sig_path))] = str(sig_variant)
            args[args.index(str(targets["binary"]))] = str(binary_path)
            job_path = write_job(
                name,
                job_manifest=manifest_variant,
                job_sig=sig_variant,
                job_binary=binary_path,
            )
            args.extend(["--job", str(job_path)])
            return args

        verify = _run_promoter(["verify", *common, "--quiet"])
        assert verify.returncode == 0, (verify.returncode, verify.stdout, verify.stderr)
        checks += 1

        # job обязан совпадать с проверенными путями и admission. Каждый
        # контроль ниже — отказ до store/launch, а не «предупреждение».
        def with_job(command: list[str], job_path: Path) -> list[str]:
            value = list(command)
            value[value.index("--job") + 1] = str(job_path)
            return value

        other_room = directory / "other-room"
        (other_room / "fixtures").mkdir(parents=True)
        wrong_root_job = write_job("wrong-root", job_root=other_room)
        refused = _run_promoter(["verify", *with_job(common, wrong_root_job), "--quiet"])
        assert refused.returncode != 0 and "job.root" in refused.stderr, (
            refused.returncode,
            refused.stdout,
            refused.stderr,
        )
        checks += 1

        fixture_copy = fixtures / "manifest-copy.json"
        fixture_copy.write_bytes(targets["fixture"].read_bytes())
        wrong_fixture_job = write_job("wrong-fixture", job_fixture=fixture_copy)
        refused = _run_promoter(["verify", *with_job(common, wrong_fixture_job), "--quiet"])
        assert refused.returncode != 0 and "job.fixture_manifest" in refused.stderr, (
            refused.returncode,
            refused.stderr,
        )
        checks += 1

        policy_copy = directory / "policy-copy.json"
        policy_copy.write_bytes(targets["policy"].read_bytes())
        wrong_check_job = write_job(
            "wrong-check", check_overrides={"policy_digest": policy_copy}
        )
        refused = _run_promoter(["verify", *with_job(common, wrong_check_job), "--quiet"])
        assert refused.returncode != 0 and "job.checks.policy_digest" in refused.stderr, (
            refused.returncode,
            refused.stderr,
        )
        checks += 1

        anchor_copy = directory / "anchor-copy.json"
        anchor_copy.write_bytes(anchor_bytes)
        wrong_anchor_job = write_job("wrong-anchor", job_anchor=anchor_copy)
        refused = _run_promoter(["verify", *with_job(common, wrong_anchor_job), "--quiet"])
        assert refused.returncode != 0 and "job.admission.anchor" in refused.stderr, (
            refused.returncode,
            refused.stderr,
        )
        checks += 1

        override_job = write_job("override")
        override_value = json.loads(override_job.read_text(encoding="utf-8"))
        override_value["cases"][0]["fixture_manifest"] = str(targets["fixture"])
        override_job.write_text(
            json.dumps(override_value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        refused = _run_promoter(["verify", *with_job(common, override_job), "--quiet"])
        assert refused.returncode != 0 and "per-case override" in refused.stderr, (
            refused.returncode,
            refused.stderr,
        )
        checks += 1

        duplicated = _run_promoter(
            ["verify", *common, "--job", str(base_job), "--quiet"]
        )
        assert duplicated.returncode != 0 and "более одного раза" in duplicated.stderr
        checks += 1

        missing_job = _run_promoter(["promote", *no_job_common])
        assert missing_job.returncode != 0 and "требует --job" in missing_job.stderr, (
            missing_job.returncode,
            missing_job.stderr,
        )
        checks += 1

        if sys.platform.startswith("linux"):
            before_launch = _run_promoter(
                ["promote", *with_job(common, wrong_root_job), "--arg", "0"]
            )
            assert before_launch.returncode != 0 and "job.root" in before_launch.stderr, (
                before_launch.returncode,
                before_launch.stdout,
                before_launch.stderr,
            )
            assert "HEAD-SLICE-R1" not in before_launch.stdout
            checks += 1

        no_permission = [item for item in common if item != "--allow-test-only"]
        refused = _run_promoter(["verify", *no_permission, "--quiet"])
        assert refused.returncode != 0 and "K11_ADMISSION_REQUIRED" in refused.stderr
        checks += 1

        # Карточка должна быть того же инструмента: digest без семантики не
        # доказывает, что допущенный binary и карточка описывают один tool.
        bad_card = directory / "bad-card.json"
        bad_card.write_bytes(b'{"id":"other","schema_version":"tool-card-v1"}\n')
        bad_manifest_value = dict(manifest)
        bad_manifest_value["card_digest"] = admission.digest_file(bad_card)
        bad_manifest_path = directory / "bad-card-manifest.json"
        bad_manifest_path.write_text(
            json.dumps(bad_manifest_value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        bad_sig_path = directory / "bad-card.sig"
        bad_sig_path.write_text(
            admission.sign_manifest(bad_manifest_path.read_bytes(), key) + "\n",
            encoding="ascii",
        )
        bad_args = list(common)
        bad_args[bad_args.index(str(manifest_path))] = str(bad_manifest_path)
        bad_args[bad_args.index(str(sig_path))] = str(bad_sig_path)
        bad_args[bad_args.index(str(targets["card"]))] = str(bad_card)
        refused = _run_promoter(["verify", *bad_args, "--quiet"])
        assert refused.returncode != 0 and "не совпадает с tool" in refused.stderr, (
            refused.returncode,
            refused.stdout,
            refused.stderr,
        )
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
        assert {
            "manifest.json",
            "manifest.sig",
            "anchor.json",
            "binary",
            "job.json",
            "promotion.json",
        } <= names
        assert not any("seed" in name for name in names)
        promotion = json.loads((stored / "promotion.json").read_text(encoding="utf-8"))
        assert promotion["exact_bytes"]["manifest"] == admission.digest_file(stored / "manifest.json")
        assert promotion["exact_bytes"]["signature"] == admission.digest_file(stored / "manifest.sig")
        assert promotion["exact_bytes"]["anchor"] == admission.digest_file(stored / "anchor.json")
        assert promotion["exact_bytes"]["job"] == admission.digest_file(stored / "job.json")
        assert promotion["digests"]["binary_digest"] == admission.digest_file(stored / "binary")
        assert promotion["job"]["sha256"] == promotion["exact_bytes"]["job"]
        checks += 1

        # store обязан писать ровно проверенные байты: подмена между verify и
        # store — отказ, а не «доказательство» с чужим binary.
        store_args = argparse.Namespace(
            manifest=str(manifest_path),
            sig=str(sig_path),
            anchor=str(anchor_path),
            card=str(targets["card"]),
            source=str(targets["source"]),
            binary=str(targets["binary"]),
            fixture=str(targets["fixture"]),
            policy=str(targets["policy"]),
            room=str(targets["room"]),
            job=str(base_job),
            now="2026-06-01T00:00:00Z",
            allow_test_only=True,
            store=str(directory / "poison-store"),
            quiet=True,
        )
        verified = verify_all(store_args)
        admitted_binary = targets["binary"].read_bytes()
        targets["binary"].write_bytes(admitted_binary[:-1] + bytes([admitted_binary[-1] ^ 1]))
        try:
            try:
                store(verified, store_args)
            except PromoterError as exc:
                assert "binary изменился" in str(exc), exc
            else:
                raise AssertionError("store принял подменённый binary")
        finally:
            targets["binary"].write_bytes(admitted_binary)
        assert not Path(store_args.store).exists(), "частичный store остался на диске"
        checks += 1

        # Изоляция запуска: окружение хоста не утекает, memfd закрыт на exec.
        if sys.platform.startswith("linux"):
            sentinel = "herness-audit-sentinel-must-not-leak"
            fd_probe = (
                'import os; print(sorted(os.readlink("/proc/self/fd/"+fd) '
                'for fd in os.listdir("/proc/self/fd") '
                'if os.path.exists("/proc/self/fd/"+fd)))'
            )
            for name, binary_name, expected_absent, extra in (
                (
                    "env",
                    "sh",
                    sentinel,
                    ["--arg=-c", '--arg=printf %s "$HERNESS_AUDIT_SENTINEL"'],
                ),
                (
                    "fd",
                    "python3",
                    "herness-promoter",
                    ["--arg=-c", f"--arg={fd_probe}"],
                ),
            ):
                binary_path = shutil.which(binary_name)
                if not binary_path:
                    continue
                args = variant(Path(binary_path), name)
                launched = _run_promoter(
                    [
                        "promote",
                        *args,
                        "--now",
                        "2026-06-01T00:00:00Z",
                        "--allow-test-only",
                        *extra,
                    ],
                    env={**os.environ, "HERNESS_AUDIT_SENTINEL": sentinel},
                )
                assert launched.returncode == 0, (
                    name,
                    launched.returncode,
                    launched.stdout,
                    launched.stderr,
                )
                assert expected_absent not in launched.stdout, (name, launched.stdout)
                checks += 1

        # seal/netprobe вне v0 — отказ до запуска
        seal_card = directory / "seal-card.json"
        seal_card.write_bytes(b'{"id":"seal","schema_version":"tool-card-v1"}\n')
        seal_manifest = dict(manifest)
        seal_manifest["tool"] = "seal"
        seal_manifest["card_digest"] = admission.digest_file(seal_card)
        seal_bytes = admission.canonical(seal_manifest)
        seal_signature = key.sign(admission.DOMAIN + b"\n" + seal_bytes).hex()
        (directory / "seal.json").write_bytes(seal_bytes)
        (directory / "seal.sig").write_text(seal_signature + "\n", encoding="ascii")
        seal_args = [item for item in no_job_common]
        seal_args[seal_args.index(str(manifest_path))] = str(directory / "seal.json")
        seal_args[seal_args.index(str(sig_path))] = str(directory / "seal.sig")
        seal_args[seal_args.index(str(targets["card"]))] = str(seal_card)
        result = _run_promoter(["promote", *seal_args])
        assert result.returncode != 0 and "вне v0" in result.stderr, (
            result.returncode,
            result.stdout,
            result.stderr,
        )
        checks += 1

        # Просроченный admission: подпись верна, срок нет.
        expired = _run_promoter(
            ["verify", *base_without_job, "--now", "2028-01-01T00:00:00Z",
             "--allow-test-only", "--quiet"]
        )
        assert expired.returncode != 0 and "просрочен" in expired.stderr
        checks += 1

        # Отозванный epoch: anchor меняется, подпись та же.
        revoked = json.loads(anchor_bytes)
        revoked["revoked_epochs"] = [1]
        revoked_path = directory / "revoked-anchor.json"
        revoked_path.write_bytes(admission.canonical(revoked))
        revoked_args = list(no_job_common)
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
        wrong_path = directory / "wrong-anchor-public.json"
        wrong_path.write_bytes(admission.canonical(wrong))
        wrong_args = list(no_job_common)
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
        subparser.add_argument("--job", action="append")
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
