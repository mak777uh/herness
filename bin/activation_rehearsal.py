"""ACTIVATION-REHEARSAL-R1: test-only допуск, promoter, head и песочный реестр.

Прибор отвечает на два вопроса одновременно:

1. работает ли вся цепочка `manifest → sign → verify → promoter → head` на
   эфемерном test-only ключе;
2. остаётся ли test-only событие в реестре `admitted_inactive`, а production
   `active` — пустым.

Это не активация. Настоящий owner-ключ здесь не создаётся, production-файлы
реестра не переписываются, `K9_proven` не выдаётся. На Linux (WSL) прибор
запускает `head_slice_host` через promoter: memfd + `F_SEAL_*` + `execveat`.
На Windows доступны verify/store и песочный реестр, запуск — N/A с причиной.

    python bin/activation_rehearsal.py --no-launch
    python bin/activation_rehearsal.py --build --evidence research/outputs/ACTIVATION-REHEARSAL-R1-2026-11-17.txt
"""

from __future__ import annotations

import argparse
import calendar
import datetime as _datetime
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"
sys.path.insert(0, str(BIN))

import admission as adm  # noqa: E402
import registry_state as rs  # noqa: E402

CARD = ROOT / "lab" / "tools" / "cards" / "head.json"
SOURCE = ROOT / "core-rs" / "src" / "head.rs"
BINARY = ROOT / "core-rs" / "target" / "release" / "head_slice_host"
FIXTURE = ROOT / "lab" / "fixtures" / "model_visible" / "head-slice.txt"
FIXTURE_MANIFEST = ROOT / "lab" / "fixtures" / "model_visible" / "manifest.json"
POLICY = ROOT / "lab" / "tools" / "policy.json"
ROOM_PROFILE = ROOT / "lab" / "tools" / "room-profile-v0.json"
MARKER = "HEAD-SLICE-R1"
NOW_TEXT = "2026-11-17T12:00:00Z"
NOW_UNIX = calendar.timegm(_datetime.datetime(2026, 11, 17, 12, 0, 0).timetuple())


class RehearsalError(Exception):
    pass


class Rehearsal:
    def __init__(self, work: Path) -> None:
        self.work = work
        self.checks: list[tuple[bool, str]] = []
        self.notes: list[str] = []
        self.commands: list[dict[str, Any]] = []
        self.records: dict[str, Any] = {}
        self.artifacts: dict[str, Path] = {}
        self.digests: dict[str, str] = {}
        self.key_fingerprint = ""
        self.manifest_digest = ""
        self.registry_event_digest = ""
        self.launch: dict[str, Any] | None = None
        self.launch_ok = False
        self.launch_state = "not-run"

    def check(self, flag: bool, name: str) -> None:
        self.checks.append((bool(flag), name))

    def note(self, text: str) -> None:
        self.notes.append(text)

    def run(self, command: list[str], timeout: int = 120, cwd: Path = ROOT) -> subprocess.CompletedProcess:
        started = time.time()
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        self.commands.append(
            {
                "command": command,
                "cwd": str(cwd),
                "rc": result.returncode,
                "seconds": round(time.time() - started, 3),
                "stdout_tail": (result.stdout or "")[-3000:],
                "stderr_tail": (result.stderr or "")[-3000:],
            }
        )
        return result


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def sha256(path: Path) -> str:
    return adm.digest_file(path)


def inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


def make_work(path: str | None) -> Path:
    if path:
        work = Path(path).expanduser().resolve()
    else:
        work = Path(tempfile.mkdtemp(prefix="herness-activation-")).resolve()
    if inside_repo(work):
        raise RehearsalError("рабочий каталог должен быть вне репозитория (seed не в git)")
    work.mkdir(parents=True, exist_ok=True)
    return work


def copy_artifacts(rehearsal: Rehearsal) -> None:
    artifacts = rehearsal.work / "artifacts"
    room = rehearsal.work / "room"
    fixtures = room / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    targets = {
        "card": artifacts / "card.json",
        "source": artifacts / "head.rs",
        "binary": artifacts / "binary",
        "policy": artifacts / "policy.json",
        "room": artifacts / "room.json",
    }
    for source, target in (
        (CARD, targets["card"]),
        (SOURCE, targets["source"]),
        (BINARY, targets["binary"]),
        (POLICY, targets["policy"]),
        (ROOM_PROFILE, targets["room"]),
        (FIXTURE_MANIFEST, fixtures / "manifest.json"),
        (FIXTURE, fixtures / "head-slice.txt"),
    ):
        if not source.exists():
            raise RehearsalError(f"нет входного файла {source}")
        write(target, source.read_bytes())
    targets["fixture"] = fixtures / "manifest.json"
    rehearsal.artifacts = targets
    rehearsal.digests = {name: sha256(path) for name, path in targets.items()}
    rehearsal.check(
        rehearsal.digests["card"] == "sha256:361ad2ecd421fae57f7ec3ae4c5e7e5bc8befd4d6d21b68573c23a70e699fe97",
        "карточка head совпадает с запечатанной HEAD-SLICE-R1",
    )


def build_binary(rehearsal: Rehearsal, enabled: bool) -> None:
    if not enabled:
        rehearsal.note("сборка не запрошена: используется существующий ELF; соответствие source→binary не доказано")
        return
    if not sys.platform.startswith("linux"):
        rehearsal.note("--build N/A: сборка head_slice_host в этом приборе только на Linux")
        return
    result = rehearsal.run(
        ["cargo", "build", "--release", "--bin", "head_slice_host"],
        timeout=600,
        cwd=ROOT / "core-rs",
    )
    rehearsal.check(result.returncode == 0, "cargo build --release --bin head_slice_host")
    if result.returncode != 0:
        raise RehearsalError("сборка head_slice_host не удалась")
    rehearsal.check(BINARY.exists(), "собранный head_slice_host существует")
    write(rehearsal.artifacts["binary"], BINARY.read_bytes())
    rehearsal.digests["binary"] = sha256(rehearsal.artifacts["binary"])


def make_key(rehearsal: Rehearsal) -> tuple[Path, Path, Path]:
    key_path, anchor_path, fingerprint = adm.create_test_key(rehearsal.work / "keys")
    rehearsal.key_fingerprint = fingerprint
    rehearsal.check(not inside_repo(key_path), "test-key лежит вне репозитория")
    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    rehearsal.check(anchor.get("test_only") is True, "anchor помечен test_only=true")
    return key_path, anchor_path, key_path


def make_manifest(rehearsal: Rehearsal, key_path: Path, anchor_path: Path) -> tuple[Path, Path]:
    key = adm.load_private_key(key_path)
    anchor_bytes = anchor_path.read_bytes()
    fingerprint, _public, _min_epoch, _revoked, expected_prev = adm.load_anchor(anchor_bytes)
    document: dict[str, Any] = {
        "schema": "herness-admission-v1",
        "kind": "tool_admission",
        "tool": "head",
        "key_fingerprint": fingerprint,
        "epoch": 1,
        "seq": 1,
        "prev": expected_prev,
        "not_before": "2026-01-01T00:00:00Z",
        "not_after": "2027-01-01T00:00:00Z",
        "test_only": True,
    }
    for field in adm.DIGEST_FIELDS:
        document[field] = rehearsal.digests[field.removesuffix("_digest")]
    manifest_path = rehearsal.work / "admission" / "manifest.json"
    manifest_bytes = adm.canonical(document) + b"\n"
    write(manifest_path, manifest_bytes)
    signature = adm.sign_manifest(manifest_bytes, key)
    sig_path = rehearsal.work / "admission" / "manifest.sig"
    write(sig_path, (signature + "\n").encode("ascii"))
    rehearsal.manifest_digest = adm.digest_bytes(manifest_bytes)
    rehearsal.check(len(signature) == 128, "detached подпись — 128 hex (64 байта)")
    return manifest_path, sig_path


def verify_admission(rehearsal: Rehearsal, manifest: Path, sig: Path, anchor: Path) -> dict[str, Any]:
    manifest_bytes = manifest.read_bytes()
    signature = sig.read_text(encoding="ascii")
    anchor_bytes = anchor.read_bytes()
    refused = False
    try:
        adm.verify_admission(manifest_bytes, signature, anchor_bytes, NOW_UNIX, allow_test_only=False)
    except adm.AdmissionError as exc:
        refused = "test-only" in str(exc) and "K11_ADMISSION_REQUIRED" in str(exc)
        rehearsal.note(f"без --allow-test-only: {exc}")
    rehearsal.check(refused, "test-only без явного разрешения отвергнут K11")
    result = adm.verify_admission(
        manifest_bytes, signature, anchor_bytes, NOW_UNIX, allow_test_only=True
    )
    rehearsal.check(result.get("signature_ok") is True, "подпись проверена")
    rehearsal.check(result.get("test_only") is True, "verify видит test_only=true")
    checks = [f"{field}={rehearsal.artifacts[field.removesuffix('_digest')]}" for field in adm.DIGEST_FIELDS]
    adm.verify_checks(result, checks)
    rehearsal.check(True, "шесть exact-byte digest совпадают")
    return result


def negative_tamper(rehearsal: Rehearsal, manifest: Path, sig: Path, anchor: Path) -> None:
    original = rehearsal.artifacts["card"].read_bytes()
    tampered = rehearsal.work / "artifacts" / "tampered-card.json"
    write(tampered, original[:-1] + bytes([original[-1] ^ 1]))
    result = adm.verify_admission(
        manifest.read_bytes(), sig.read_text(encoding="ascii"), anchor.read_bytes(), NOW_UNIX, True
    )
    refused = False
    try:
        adm.verify_checks(result, [f"card_digest={tampered}"])
    except adm.AdmissionError as exc:
        refused = "K11_ADMISSION_REQUIRED" in str(exc)
        rehearsal.note(f"tampered card: {exc}")
    rehearsal.check(refused, "один изменённый байт карточки отвергнут")
    rehearsal.check(tampered.read_bytes() != original, "tampered-копия действительно изменена")


def promoter_common(
    rehearsal: Rehearsal, manifest: Path, sig: Path, anchor: Path, store: Path | None = None
) -> list[str]:
    args = [
        "--manifest", str(manifest),
        "--sig", str(sig),
        "--anchor", str(anchor),
        "--card", str(rehearsal.artifacts["card"]),
        "--source", str(rehearsal.artifacts["source"]),
        "--binary", str(rehearsal.artifacts["binary"]),
        "--fixture", str(rehearsal.artifacts["fixture"]),
        "--policy", str(rehearsal.artifacts["policy"]),
        "--room", str(rehearsal.artifacts["room"]),
        "--now", NOW_TEXT,
    ]
    if store is not None:
        args += ["--store", str(store)]
    return args


def promoter_command(
    rehearsal: Rehearsal,
    manifest: Path,
    sig: Path,
    anchor: Path,
    command: str,
    store: Path | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    return [
        sys.executable,
        str(BIN / "promoter.py"),
        command,
        *promoter_common(rehearsal, manifest, sig, anchor, store),
        *(extra or []),
    ]


def promoter_checks(rehearsal: Rehearsal, manifest: Path, sig: Path, anchor: Path) -> None:
    without = rehearsal.run(promoter_command(rehearsal, manifest, sig, anchor, "verify"))
    rehearsal.check(
        without.returncode != 0 and "K11_ADMISSION_REQUIRED" in (without.stderr or ""),
        "promoter verify без --allow-test-only отвергает test-only",
    )
    store = rehearsal.work / "store"
    allowed = rehearsal.run(
        promoter_command(
            rehearsal, manifest, sig, anchor, "verify", store, ["--allow-test-only"]
        )
    )
    rehearsal.check(allowed.returncode == 0, "promoter verify с --allow-test-only проходит")
    promotion = store / "promotion.json"
    rehearsal.check(promotion.exists(), "promoter store создал promotion.json")
    if promotion.exists():
        summary = json.loads(promotion.read_text(encoding="utf-8"))
        rehearsal.check(summary.get("test_only") is True, "store сохраняет test_only=true")
        rehearsal.check(summary.get("tool") == "head", "store относится к head")
        names = {item.name for item in store.iterdir()}
        rehearsal.check(not any("seed" in name for name in names), "в store нет private seed")
    else:
        rehearsal.check(False, "promotion.json отсутствует")


def registry_sandbox(rehearsal: Rehearsal, manifest: Path) -> dict[str, Any]:
    before = {
        "snapshot": sha256(rs.SNAPSHOT),
        "events": sha256(rs.EVENTS),
        "state": sha256(rs.STATE),
    }
    sandbox = rehearsal.work / "registry"
    sandbox.mkdir(parents=True, exist_ok=True)
    for source, name in ((rs.SNAPSHOT, "registry.jsonl"), (rs.EVENTS, "registry.events.jsonl"), (rs.POLICY, "policy.json")):
        write(sandbox / name, source.read_bytes())
    snapshot = sandbox / "registry.jsonl"
    events_path = sandbox / "registry.events.jsonl"
    policy = sandbox / "policy.json"
    rows = rs.read_snapshot(snapshot)
    events = rs.read_events(events_path)
    snapshot_digest = rs.digest_file(snapshot)
    policy_digest = rs.digest_file(policy)
    record = {
        "schema": "activation-rehearsal-record-v1",
        "run": "ACTIVATION-REHEARSAL-R1",
        "at": NOW_TEXT,
        "test_only": True,
        "key_fingerprint": rehearsal.key_fingerprint,
        "manifest_digest": rehearsal.manifest_digest,
        "artifacts": rehearsal.digests,
    }
    evidence_digest = adm.digest_bytes(adm.canonical(record))
    event = {
        "schema": rs.EVENT_SCHEMA,
        "seq": len(events),
        "prev": rs.line_hash(events[-1][0]),
        "type": "admitted",
        "tool_id": "head",
        "at": NOW_TEXT,
        "body": {
            "reason": "ACTIVATION-REHEARSAL-R1: test-only; production active не меняется",
            "owner_signed": True,
            "test_only": True,
            "admission_digest": rehearsal.manifest_digest,
            "evidence_digest": evidence_digest,
        },
    }
    line = rs.canonical(event)
    base = [item[0] for item in events]
    events_path.write_bytes(b"\n".join([*base, line]) + b"\n")
    rehearsal.registry_event_digest = rs.line_hash(line)
    state = rs.computed_state(snapshot=snapshot, events=events_path, policy=policy)
    head = state.get("tools", {}).get("head", {})
    rehearsal.check(head.get("state") == "admitted_inactive", "песочный head = admitted_inactive")
    rehearsal.check(state.get("active") == [], "песочный active пуст")
    ok, message = rs.authorize_state(state, "head")
    rehearsal.check(not ok and "admitted_inactive" in message, "authorize_state отказывает test-only head")
    after = {
        "snapshot": sha256(rs.SNAPSHOT),
        "events": sha256(rs.EVENTS),
        "state": sha256(rs.STATE),
    }
    rehearsal.check(before == after, "production registry-файлы не изменены")
    production = rs.computed_state()
    rehearsal.check(production.get("tools", {}).get("head", {}).get("state") == "candidate",
                    "production head остаётся candidate")
    rehearsal.check(production.get("active") == [], "production active пуст")
    return state


def make_job(rehearsal: Rehearsal, manifest: Path, sig: Path, anchor: Path) -> Path:
    room = rehearsal.work / "room"
    fixtures = room / "fixtures"
    checks = {
        "card_digest": str(rehearsal.artifacts["card"]),
        "source_digest": str(rehearsal.artifacts["source"]),
        "binary_digest": str(rehearsal.artifacts["binary"]),
        "fixture_digest": str(rehearsal.artifacts["fixture"]),
        "policy_digest": str(rehearsal.artifacts["policy"]),
        "room_digest": str(rehearsal.artifacts["room"]),
    }
    cases = [
        {
            "id": "normal",
            "path_ref": {"root_ref": "room:input", "segments": ["fixtures", "head-slice.txt"]},
            "line_count": 3,
            "max_bytes_read": 4096,
        },
        {
            "id": "outside-root",
            "path_ref": {"root_ref": "host:/", "segments": ["etc", "passwd"]},
            "line_count": 3,
            "max_bytes_read": 4096,
        },
    ]
    job = {
        "root": str(room),
        "now_unix": NOW_UNIX,
        "fixture_manifest": str(fixtures / "manifest.json"),
        "admission": {"manifest": str(manifest), "sig": str(sig), "anchor": str(anchor)},
        "checks": checks,
        "cases": cases,
    }
    path = rehearsal.work / "job.json"
    write(path, (json.dumps(job, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return path


def parse_records(text: str) -> list[dict[str, Any]]:
    records = []
    for line in text.replace("\r", "").splitlines():
        if MARKER not in line:
            continue
        raw = line.split(MARKER, 1)[1].strip()
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError:
            records.append({"id": "__parse__", "outcome": "error", "error": raw})
    return records


def launch(
    rehearsal: Rehearsal,
    manifest: Path,
    sig: Path,
    anchor: Path,
    enabled: bool,
    allow_test_only: bool = True,
) -> None:
    if not enabled:
        rehearsal.note("launch N/A: --no-launch; promoter launch не проверялся")
        rehearsal.launch_state = "n/a"
        return
    if not sys.platform.startswith("linux"):
        rehearsal.note("launch N/A: promoter запускает только на Linux; verify/store проверены")
        rehearsal.launch_state = "n/a"
        return
    job = make_job(rehearsal, manifest, sig, anchor)
    extra = ["--job", str(job)]
    if allow_test_only:
        extra.insert(0, "--allow-test-only")
    command = promoter_command(
        rehearsal,
        manifest,
        sig,
        anchor,
        "promote",
        rehearsal.work / "store-launch",
        extra,
    )
    result = rehearsal.run(command, timeout=120)
    text = (result.stdout or "") + (result.stderr or "")
    records = parse_records(text)
    normal = next((item for item in records if item.get("id") == "normal"), None)
    outside = next((item for item in records if item.get("id") == "outside-root"), None)
    rehearsal.launch = {
        "command": command,
        "rc": result.returncode,
        "stdout_tail": (result.stdout or "")[-4000:],
        "stderr_tail": (result.stderr or "")[-4000:],
        "records": records,
    }
    rehearsal.check(result.returncode == 0, "promoter promote завершился rc=0")
    rehearsal.check("execveat-memfd" in text, "запуск через memfd/execveat, без path fallback")
    rehearsal.check(
        "job_sha256" in text and "memfd:fd" in text,
        "job передан запечатанным memfd, а не путём",
    )
    rehearsal.check("activation" in text and "none" in text, "promoter не меняет activation")
    rehearsal.check(normal is not None and normal.get("outcome") == "ok", "normal: outcome=ok")
    if normal:
        rehearsal.check(len(normal.get("lines") or []) == 3, "normal: 3 строки")
        rehearsal.check(normal.get("bytes_read") == 144, "normal: bytes_read=144")
        rehearsal.check(normal.get("truncated") is True, "normal: truncated=true")
        rehearsal.check(normal.get("stop_reason") == "line_cap", "normal: stop_reason=line_cap")
    rehearsal.check(
        outside is not None and outside.get("code") == "S6_CLOSURE_BREACH",
        "outside-root: S6_CLOSURE_BREACH",
    )
    launch_flags = [
        flag
        for flag, name in rehearsal.checks
        if name.startswith(("promoter promote", "запуск через", "job передан",
                            "promoter не меняет", "normal:", "outside-root:"))
    ]
    rehearsal.launch_ok = bool(launch_flags) and all(launch_flags)
    rehearsal.launch_state = "passed" if rehearsal.launch_ok else "failed"


def evidence_text(rehearsal: Rehearsal) -> str:
    passed = sum(1 for flag, _ in rehearsal.checks if flag)
    total = len(rehearsal.checks)
    lines = [
        "# ACTIVATION-REHEARSAL-R1 — test-only допуск, promoter и песочный реестр",
        "",
        f"Дата: 2026-11-17; хост: {platform.platform()}; Python: {platform.python_version()}",
        "Режим: test-only; настоящий owner-ключ не создавался; production active не менялся.",
        "",
        "## Ключ и манифест",
        "",
        f"- key_fingerprint: `{rehearsal.key_fingerprint}` (private seed не печатается и лежит вне репозитория)",
        f"- manifest_digest: `{rehearsal.manifest_digest}`",
        "- test_only: true; epoch=1; seq=1; prev=GENESIS",
        "",
        "## Точные входы",
        "",
    ]
    for name in ("card", "source", "binary", "fixture", "policy", "room"):
        lines.append(f"- {name}: `{rehearsal.digests.get(name, '')}`")
    lines += ["", "## Проверки", ""]
    for flag, name in rehearsal.checks:
        lines.append(f"- [{'ok' if flag else 'FAIL'}] {name}")
    if rehearsal.notes:
        lines += ["", "## Примечания и N/A", ""]
        lines += [f"- {note}" for note in rehearsal.notes]
    lines += ["", "## Команды", ""]
    for item in rehearsal.commands:
        lines.append(f"- `{' '.join(item['command'])}`; cwd={item['cwd']}; rc={item['rc']}; {item['seconds']} с")
        if item.get("stdout_tail"):
            lines.append("```text")
            lines.append(item["stdout_tail"].rstrip())
            lines.append("```")
        if item.get("stderr_tail"):
            lines.append("```text")
            lines.append(item["stderr_tail"].rstrip())
            lines.append("```")
    if rehearsal.launch:
        lines += ["", "## Launch", "", f"rc: {rehearsal.launch['rc']}", "```json"]
        lines.append(json.dumps(rehearsal.launch["records"], ensure_ascii=False, indent=1))
        lines += ["```"]
    def group_passed(*prefixes: str) -> bool:
        flags = [
            flag
            for flag, name in rehearsal.checks
            if name.startswith(prefixes)
        ]
        return bool(flags) and all(flags)

    lines += [
        "",
        "## Что это доказывает",
        "",
        f"- {passed} из {total} проверок прошли; итог — ниже, а не в этом списке.",
    ]
    if group_passed("test-only без", "подпись проверена", "verify видит",
                    "шесть exact-byte", "один изменённый", "tampered-копия"):
        lines.append(
            "- Манифест: подпись и шесть exact-byte digest проверены; без "
            "`--allow-test-only` test-only отвергнут; изменённый байт отвергнут."
        )
    if group_passed("promoter verify", "promoter store", "store сохраняет",
                    "store относится", "в store нет"):
        lines.append("- Promoter verify/store выполнены; store сохраняет test_only=true и не содержит seed.")
    if group_passed("песочный head", "песочный active", "authorize_state"):
        lines.append("- Test-only admitted-событие в песочном реестре даёт `admitted_inactive`; `authorize_state` отказывает.")
    if group_passed("production registry", "production head", "production active"):
        lines.append("- Production `head` остаётся candidate; production `active` пуст; registry-файлы не изменены.")
    if rehearsal.launch_state == "passed":
        lines.append("- Launch подтверждён: head_slice_host запущен через memfd/execveat; normal и outside-root совпали с ожиданием.")
    elif rehearsal.launch_state == "n/a":
        lines.append("- Launch: N/A с причиной (см. примечания); это не зелёный результат.")
    else:
        lines.append("- Launch НЕ подтверждён этим прогоном; см. FAIL выше и раздел Launch.")
    if passed < total:
        lines.append("- Часть проверок провалена: утверждения выше относятся только к зелёным группам.")
    lines += [
        "",
        "## Что это не доказывает",
        "",
        "- Test-only ключ не является owner-ключом и не заменяет настоящую церемонию.",
        "- Реестр не проверяет подпись; её проверяет promoter. `test_only:false` — объявленное поле.",
        "- `run_tool_g` не имеет ветки `head`: conversational loop не запускает head и после активации;",
        "  запуск идёт через promoter. Это отдельный разрыв, не закрашенный этим прогоном.",
        "- QEMU/KVM повторно не запускался; HEAD-SLICE-R1 evidence не переписывалось.",
        "- `K9_proven` не выдавался.",
        "",
        f"Итог: {'PASS' if passed == total else 'FAIL'} ({passed}/{total})",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="test-only активационная репетиция head")
    parser.add_argument("--work", help="рабочий каталог вне репозитория")
    parser.add_argument("--build", action="store_true", help="собрать head_slice_host (Linux)")
    parser.add_argument("--no-launch", action="store_true", help="только verify/store и песочный реестр")
    parser.add_argument("--evidence", help="записать отчёт в этот файл")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--keep", action="store_true", help="не удалять рабочий каталог")
    args = parser.parse_args(argv)
    work: Path | None = None
    rehearsal: Rehearsal | None = None
    try:
        work = make_work(args.work)
        rehearsal = Rehearsal(work)
        copy_artifacts(rehearsal)
        build_binary(rehearsal, args.build)
        key_path, anchor_path, _ = make_key(rehearsal)
        manifest, sig = make_manifest(rehearsal, key_path, anchor_path)
        verify_admission(rehearsal, manifest, sig, anchor_path)
        negative_tamper(rehearsal, manifest, sig, anchor_path)
        promoter_checks(rehearsal, manifest, sig, anchor_path)
        registry_sandbox(rehearsal, manifest)
        launch(rehearsal, manifest, sig, anchor_path, not args.no_launch)
        text = evidence_text(rehearsal)
        if args.evidence:
            target = Path(args.evidence)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        report = work / "evidence.txt"
        report.write_text(text, encoding="utf-8")
        if not args.quiet:
            for flag, name in rehearsal.checks:
                print(f"[{'ok' if flag else 'FAIL'}] {name}")
            print(f"рабочий каталог: {work}")
            print(f"отчёт: {report}")
            if args.evidence:
                print(f"evidence: {Path(args.evidence)}")
        failed = sum(1 for flag, _ in rehearsal.checks if not flag)
        print(f"PASS activation rehearsal: {len(rehearsal.checks) - failed}/{len(rehearsal.checks)}"
              if failed == 0 else f"FAIL activation rehearsal: провалов {failed}")
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        return 0 if failed == 0 else 1
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL activation rehearsal: {exc}", file=sys.stderr)
        if rehearsal is not None and work is not None:
            try:
                text = evidence_text(rehearsal) + f"\nОшибка: {exc}\n"
                report = work / "evidence-fail.txt"
                report.write_text(text, encoding="utf-8")
                print(f"отчёт о сбое: {report}", file=sys.stderr)
                if not args.keep:
                    shutil.rmtree(work, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
