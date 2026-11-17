"""OWNER-CEREMONY-DRY-RUN-R1: положительная ветка допуска в песочнице.

Прибор отвечает на вопрос, который не проверяет test-only репетиция: если манифест
подписан ключом с anchor `test_only:false`, проходит ли цепочка
`manifest → verify → promoter → head` **без** `--allow-test-only` и даёт ли
песочное событие `admitted` состояние `active`.

Ключ здесь эфемерный, а anchor с `test_only:false` — только объявление для
песочницы. Это не настоящий owner-ключ, не approval и не активация production.
Production `registry.jsonl`, `registry.events.jsonl`, `registry.state.json` не
переписываются; `K9_proven` не выдаётся. На Linux (WSL) запуск идёт через
promoter: memfd + `F_SEAL_*` + `execveat`; на Windows доступны verify/store и
песочный реестр, запуск — N/A с причиной.

    python bin/owner_ceremony_dry_run.py --no-launch
    python bin/owner_ceremony_dry_run.py --build \\
        --evidence research/outputs/OWNER-CEREMONY-DRY-RUN-R1-2026-11-17.txt
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"
sys.path.insert(0, str(BIN))

import activation_rehearsal as ar  # noqa: E402
import admission as adm  # noqa: E402
import registry_state as rs  # noqa: E402

MARKER = "OWNER-CEREMONY-DRY-RUN-R1"
NOW_TEXT = ar.NOW_TEXT
NOW_UNIX = ar.NOW_UNIX


def make_key(rehearsal: ar.Rehearsal) -> tuple[Path, Path]:
    key_path, anchor_path, fingerprint = adm.create_ephemeral_key(
        rehearsal.work / "keys", test_only=False, name="owner-dry-run"
    )
    rehearsal.key_fingerprint = fingerprint
    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    rehearsal.check(not ar.inside_repo(key_path), "эфемерный ключ лежит вне репозитория")
    rehearsal.check(anchor.get("test_only") is False, "anchor помечен test_only=false (симуляция owner)")
    rehearsal.check(anchor.get("key_fingerprint") == fingerprint, "fingerprint anchor совпадает")
    return key_path, anchor_path


def make_manifest(
    rehearsal: ar.Rehearsal, key_path: Path, anchor_path: Path
) -> tuple[Path, Path]:
    key = adm.load_private_key(key_path)
    fingerprint, _public, _min_epoch, _revoked, expected_prev = adm.load_anchor(
        anchor_path.read_bytes()
    )
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
        "test_only": False,
    }
    for field in adm.DIGEST_FIELDS:
        document[field] = rehearsal.digests[field.removesuffix("_digest")]
    manifest_path = rehearsal.work / "admission" / "manifest.json"
    manifest_bytes = adm.canonical(document) + b"\n"
    ar.write(manifest_path, manifest_bytes)
    signature = adm.sign_manifest(manifest_bytes, key)
    sig_path = rehearsal.work / "admission" / "manifest.sig"
    ar.write(sig_path, (signature + "\n").encode("ascii"))
    rehearsal.manifest_digest = adm.digest_bytes(manifest_bytes)
    rehearsal.check(len(signature) == 128, "detached подпись — 128 hex (64 байта)")
    return manifest_path, sig_path


def verify_positive(
    rehearsal: ar.Rehearsal, manifest: Path, sig: Path, anchor: Path
) -> dict[str, Any]:
    result = adm.verify_admission(
        manifest.read_bytes(),
        sig.read_text(encoding="ascii"),
        anchor.read_bytes(),
        NOW_UNIX,
        allow_test_only=False,
    )
    rehearsal.check(result.get("signature_ok") is True, "подпись проверена без --allow-test-only")
    rehearsal.check(result.get("test_only") is False, "verify видит test_only=false")
    checks = [
        f"{field}={rehearsal.artifacts[field.removesuffix('_digest')]}"
        for field in adm.DIGEST_FIELDS
    ]
    adm.verify_checks(result, checks)
    rehearsal.check(True, "шесть exact-byte digest совпадают")
    return result


def promoter_positive(
    rehearsal: ar.Rehearsal, manifest: Path, sig: Path, anchor: Path
) -> None:
    store = rehearsal.work / "store"
    result = rehearsal.run(ar.promoter_command(rehearsal, manifest, sig, anchor, "verify", store))
    rehearsal.check(
        result.returncode == 0,
        "promoter verify без --allow-test-only проходит для test_only=false",
    )
    promotion = store / "promotion.json"
    rehearsal.check(promotion.exists(), "promoter store создал promotion.json")
    if promotion.exists():
        summary = json.loads(promotion.read_text(encoding="utf-8"))
        rehearsal.check(summary.get("test_only") is False, "store сохраняет test_only=false")
        rehearsal.check(summary.get("tool") == "head", "store относится к head")
        names = {item.name for item in store.iterdir()}
        rehearsal.check(not any("seed" in name for name in names), "в store нет private seed")
    else:
        rehearsal.check(False, "promotion.json отсутствует")


def registry_positive(rehearsal: ar.Rehearsal, manifest: Path) -> dict[str, Any]:
    before = {
        "snapshot": ar.sha256(rs.SNAPSHOT),
        "events": ar.sha256(rs.EVENTS),
        "state": ar.sha256(rs.STATE),
    }
    sandbox = rehearsal.work / "registry"
    sandbox.mkdir(parents=True, exist_ok=True)
    for source, name in (
        (rs.SNAPSHOT, "registry.jsonl"),
        (rs.EVENTS, "registry.events.jsonl"),
        (rs.POLICY, "policy.json"),
    ):
        ar.write(sandbox / name, source.read_bytes())
    snapshot = sandbox / "registry.jsonl"
    events_path = sandbox / "registry.events.jsonl"
    policy = sandbox / "policy.json"
    rows = rs.read_snapshot(snapshot)
    events = rs.read_events(events_path)
    record = {
        "schema": "owner-ceremony-dry-run-record-v1",
        "run": MARKER,
        "at": NOW_TEXT,
        "test_only": False,
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
            "reason": f"{MARKER}: эфемерный ключ и песочница; production не меняется",
            "owner_signed": True,
            "test_only": False,
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
    rehearsal.check(head.get("state") == "active", "песочный head = active")
    rehearsal.check(state.get("active") == ["head"], "песочный active = [head]")
    ok, message = rs.authorize_state(state, "head")
    rehearsal.check(ok and message == "head", "authorize_state(head) разрешает в песочнице")
    after = {
        "snapshot": ar.sha256(rs.SNAPSHOT),
        "events": ar.sha256(rs.EVENTS),
        "state": ar.sha256(rs.STATE),
    }
    rehearsal.check(before == after, "production registry-файлы не изменены")
    production = rs.computed_state()
    rehearsal.check(
        production.get("tools", {}).get("head", {}).get("state") == "candidate",
        "production head остаётся candidate",
    )
    rehearsal.check(production.get("active") == [], "production active пуст")
    return state


def evidence_text(rehearsal: ar.Rehearsal) -> str:
    passed = sum(1 for flag, _ in rehearsal.checks if flag)
    total = len(rehearsal.checks)
    lines = [
        f"# {MARKER} — положительная ветка допуска в песочнице",
        "",
        f"Дата: 17.11.2026; хост: {platform.platform()}; Python: {platform.python_version()}",
        "Сценарий: эфемерный ключ, anchor `test_only:false`, манифест `test_only:false`.",
        "Это не настоящий owner-ключ и не approval; production не активируется.",
        "",
        "## Проверки",
        "",
    ]
    for flag, name in rehearsal.checks:
        lines.append(f"- [{'ok' if flag else 'FAIL'}] {name}")
    lines += [
        "",
        "## Входы",
        "",
    ]
    for name in sorted(rehearsal.digests):
        lines.append(f"- {name}: `{rehearsal.digests[name]}`")
    lines += [
        f"- key_fingerprint: `{rehearsal.key_fingerprint}`",
        f"- manifest_digest: `{rehearsal.manifest_digest}`",
        f"- registry_event_digest: `{rehearsal.registry_event_digest}`",
        f"- launch: {rehearsal.launch_state}",
        "",
        "## Что это доказывает",
        "",
    ]
    green = {name for flag, name in rehearsal.checks if flag}
    if any(name.startswith("подпись проверена") for name in green):
        lines.append("- Манифест с `test_only:false` проверяется без `--allow-test-only`.")
    if any(name.startswith("promoter verify") for name in green):
        lines.append("- Promoter принимает манифест и сохраняет `promotion.json` с `test_only:false`.")
    if rehearsal.launch_state == "passed":
        lines.append(
            "- head запускается через memfd/execveat; normal 3 строки/144 B/`line_cap`, "
            "outside-root — `S6_CLOSURE_BREACH`."
        )
    if any(name.startswith("песочный active") for name in green):
        lines.append("- В песочном реестре событие `admitted` с `test_only:false` даёт `active`.")
    if any(name.startswith("production registry") for name in green):
        lines.append("- Production-файлы реестра не изменены; production `head` остаётся `candidate`.")
    if passed != total:
        lines.append("- Часть проверок провалена: перечисленные выше утверждения не считаются доказанными.")
    lines += [
        "",
        "## Что это не доказывает",
        "",
        "- Эфемерный ключ не является owner-ключом; anchor `test_only:false` — объявление для песочницы.",
        "- Это не owner approval и не разрешение на production-активацию.",
        "- Реестр не верифицирует подпись; её проверяет promoter. Событие связывает `admission_digest`",
        "  (манифест содержит `key_fingerprint`), но реестр не содержит allowlist owner-anchor:",
        "  владелец обязан сверить fingerprint и anchor вне канала до добавления события.",
        "- `run_tool_g` не имеет ветки `head`: conversational loop не запускает head и после активации;",
        "  запуск идёт через promoter. Это отдельный разрыв, не закрашенный этим прогоном.",
        "- QEMU/KVM повторно не запускался; HEAD-SLICE-R1 evidence не переписывалось.",
        "- `K9_proven` не выдавался.",
        "",
        f"Итог: {'PASS' if passed == total else 'FAIL'} ({passed}/{total})",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="сухая owner-церемония в песочнице")
    parser.add_argument("--work", help="рабочий каталог вне репозитория")
    parser.add_argument("--build", action="store_true", help="собрать head_slice_host (Linux)")
    parser.add_argument("--no-launch", action="store_true", help="только verify/store и песочный реестр")
    parser.add_argument("--evidence", help="записать отчёт в этот файл")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--keep", action="store_true", help="не удалять рабочий каталог")
    args = parser.parse_args(argv)
    work: Path | None = None
    rehearsal: ar.Rehearsal | None = None
    try:
        work = ar.make_work(args.work)
        rehearsal = ar.Rehearsal(work)
        ar.copy_artifacts(rehearsal)
        ar.build_binary(rehearsal, args.build)
        key_path, anchor_path = make_key(rehearsal)
        manifest, sig = make_manifest(rehearsal, key_path, anchor_path)
        verify_positive(rehearsal, manifest, sig, anchor_path)
        promoter_positive(rehearsal, manifest, sig, anchor_path)
        registry_positive(rehearsal, manifest)
        ar.launch(rehearsal, manifest, sig, anchor_path, not args.no_launch, allow_test_only=False)
        text = evidence_text(rehearsal)
        if args.evidence:
            target = Path(args.evidence)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8"))
        report = work / "evidence.txt"
        report.write_bytes(text.encode("utf-8"))
        if not args.quiet:
            for flag, name in rehearsal.checks:
                print(f"[{'ok' if flag else 'FAIL'}] {name}")
            print(f"рабочий каталог: {work}")
            print(f"отчёт: {report}")
            if args.evidence:
                print(f"evidence: {Path(args.evidence)}")
        failed = sum(1 for flag, _ in rehearsal.checks if not flag)
        print(
            f"PASS owner ceremony dry-run: {len(rehearsal.checks) - failed}/{len(rehearsal.checks)}"
            if failed == 0
            else f"FAIL owner ceremony dry-run: провалов {failed}"
        )
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        return 0 if failed == 0 else 1
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL owner ceremony dry-run: {exc}", file=sys.stderr)
        if rehearsal is not None and work is not None:
            try:
                report = work / "evidence-fail.txt"
                report.write_bytes((evidence_text(rehearsal) + f"\nОшибка: {exc}\n").encode("utf-8"))
                print(f"отчёт: {report}", file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass
            if not args.keep:
                shutil.rmtree(work, ignore_errors=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
