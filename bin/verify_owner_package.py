"""OWNER-VERIFY-R1: read-only отчёт по пакету допуска для владельца.

Прибор отвечает на вопрос: можно ли предъявить owner-пакет (манифест, подпись,
anchor, шесть точных артефактов, fixture-содержимое, evidence) и какие проверки
он проходит **до** появления события в реестре. Он ничего не создаёт и не пишет:
ни store, ни registry, ни ключей. Private key не читается и не нужен.

По умолчанию `test_only=true` считается провалом: такой манифест не даёт права
запуска. `--allow-test-only` только осматривает тестовый пакет и не превращает
его в approval.

    python bin/verify_owner_package.py \
        --manifest /offline/manifest.json --sig /offline/manifest.sig \
        --anchor /offline/anchor.json --card ... --source ... --binary ... \
        --fixture ... --policy ... --room ... --evidence research/outputs/...
    python bin/verify_owner_package.py --self-test
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
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

MARKER = "OWNER-VERIFY-R1"
CARD = ROOT / "lab" / "tools" / "drafts" / "head-v1.draft.json"
SOURCE = ROOT / "core-rs" / "src" / "head.rs"
POLICY = ROOT / "lab" / "tools" / "policy.json"
ROOM = ROOT / "lab" / "tools" / "room-profile-v0.json"
FIXTURES = ROOT / "lab" / "fixtures" / "model_visible"


class Report:
    def __init__(self) -> None:
        self.checks: list[tuple[bool, str, str]] = []
        self.notes: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []

    def check(self, flag: bool, name: str, detail: str = "") -> None:
        self.checks.append((bool(flag), name, detail))

    def note(self, name: str, value: str) -> None:
        self.notes.append((name, value))

    def warn(self, name: str, detail: str = "") -> None:
        self.warnings.append((name, detail))

    @property
    def ok(self) -> bool:
        return all(flag for flag, _, _ in self.checks)

    @property
    def failed(self) -> int:
        return sum(1 for flag, _, _ in self.checks if not flag)

    def text(self, title: str) -> str:
        lines = [title, ""]
        for name, value in self.notes:
            lines.append(f"- {name}: {value}")
        if self.notes:
            lines.append("")
        for flag, name, detail in self.checks:
            mark = "ok" if flag else "FAIL"
            suffix = f" — {detail}" if detail else ""
            lines.append(f"[{mark}] {name}{suffix}")
        for name, detail in self.warnings:
            suffix = f" — {detail}" if detail else ""
            lines.append(f"[warn] {name}{suffix}")
        lines += [
            "",
            f"Итог: {'PASS' if self.ok else 'FAIL'} "
            f"({len(self.checks) - self.failed}/{len(self.checks)}; "
            f"предупреждений: {len(self.warnings)})",
        ]
        return "\n".join(lines) + "\n"


def _safe_relative(relative: str) -> bool:
    if not relative or relative.startswith("/") or "\\" in relative or "\0" in relative:
        return False
    if ":" in relative.split("/")[0]:
        return False
    return all(part not in ("", ".", "..") for part in relative.split("/"))


def verify_fixture_contents(manifest_path: Path, report: Report) -> None:
    try:
        document = adm.load_json_bytes(manifest_path.read_bytes(), "fixture manifest")
    except (OSError, adm.AdmissionError) as exc:
        report.check(False, "fixture manifest читается и разбирается", str(exc))
        return
    report.check(True, "fixture manifest читается и разбирается")
    if not isinstance(document, dict):
        report.check(False, "fixture manifest — объект")
        return
    accepted = document.get("accepted_classes")
    if not isinstance(accepted, list) or not all(isinstance(item, str) for item in accepted):
        report.check(False, "fixture manifest: accepted_classes — массив строк")
        return
    files = document.get("files")
    if not isinstance(files, list) or not files:
        report.check(False, "fixture manifest: files — непустой массив")
        return
    report.check(True, f"fixture manifest: объявлено файлов {len(files)}")
    base = manifest_path.parent.resolve()
    for entry in files:
        if not isinstance(entry, dict):
            report.check(False, "fixture: запись файла — объект")
            continue
        relative = entry.get("path")
        if not isinstance(relative, str) or not _safe_relative(relative):
            report.check(False, f"fixture: небезопасный путь {relative!r}")
            continue
        target = base.joinpath(*relative.split("/")).resolve()
        try:
            target.relative_to(base)
        except ValueError:
            report.check(False, f"fixture {relative}: путь выходит из каталога манифеста")
            continue
        if not target.is_file():
            report.check(False, f"fixture {relative}: regular file существует")
            continue
        report.check(True, f"fixture {relative}: regular file")
        expected_digest = entry.get("sha256")
        actual_digest = adm.digest_file(target)
        report.check(
            isinstance(expected_digest, str) and actual_digest == expected_digest,
            f"fixture {relative}: sha256 содержимого",
            "" if actual_digest == expected_digest else f"получено {actual_digest}",
        )
        size = target.stat().st_size
        report.check(
            entry.get("bytes") == size,
            f"fixture {relative}: размер содержимого",
            "" if entry.get("bytes") == size else f"получено {size}",
        )
        data_class = entry.get("data_class")
        report.check(
            isinstance(data_class, str) and data_class in accepted,
            f"fixture {relative}: класс {data_class!r} принят",
        )


def verify_package(
    *,
    manifest: Path,
    sig: Path,
    anchor: Path,
    card: Path,
    source: Path,
    binary: Path,
    fixture: Path,
    policy: Path,
    room: Path,
    now_unix: int,
    allow_test_only: bool,
    evidence: Path | None = None,
) -> Report:
    report = Report()
    artifacts = {
        "card_digest": card,
        "source_digest": source,
        "binary_digest": binary,
        "fixture_digest": fixture,
        "policy_digest": policy,
        "room_digest": room,
    }
    report.note("manifest", str(manifest))
    report.note("anchor", str(anchor))
    try:
        manifest_bytes = manifest.read_bytes()
        signature = sig.read_text(encoding="ascii")
        anchor_bytes = anchor.read_bytes()
    except OSError as exc:
        report.check(False, "входы читаются", str(exc))
        return report

    try:
        result = adm.verify_admission(
            manifest_bytes, signature, anchor_bytes, now_unix, allow_test_only=True
        )
    except adm.AdmissionError as exc:
        report.check(False, "admission: подпись, срок, epoch/seq/prev, fingerprint", str(exc))
        return report
    report.check(True, "admission: подпись, срок, epoch/seq/prev, fingerprint")
    report.note("tool", str(result["tool"]))
    report.note("epoch/seq", f"{result['epoch']}/{result['seq']}")
    report.note("test_only", str(result["test_only"]).lower())
    report.note("key_fingerprint", result["key_fingerprint"])
    report.note("manifest_digest", adm.digest_bytes(manifest_bytes))

    if result["test_only"] and not allow_test_only:
        report.check(
            False,
            "test_only=false",
            "манифест помечен test_only=true: права запуска нет; нужен owner-подпись",
        )
    else:
        report.check(True, "test_only=false" if not result["test_only"] else "test_only=true (осмотр)")

    try:
        anchor_document = adm.load_json_bytes(anchor_bytes, "anchor")
    except adm.AdmissionError as exc:
        report.check(False, "anchor разбирается", str(exc))
        anchor_document = {}
    if isinstance(anchor_document, dict):
        if anchor_document.get("test_only") is True and not result["test_only"]:
            report.check(False, "anchor не помечен test_only", "owner-манифест подписан test-only anchor")
        else:
            report.check(True, "anchor соответствует типу пакета")
        if "expected_prev" in anchor_document:
            report.note("anchor expected_prev", str(anchor_document["expected_prev"]))
        if "min_epoch" in anchor_document:
            report.note("anchor min_epoch", str(anchor_document["min_epoch"]))

    for field in adm.DIGEST_FIELDS:
        path = artifacts[field]
        try:
            adm.verify_file_digest(result["digests"][field], path)
        except adm.AdmissionError as exc:
            report.check(False, f"{field}: точные байты", str(exc))
        else:
            report.check(True, f"{field}: точные байты")

    try:
        card_document = adm.load_json_bytes(card.read_bytes(), "card")
    except (OSError, adm.AdmissionError) as exc:
        report.check(False, "card: схема и id", str(exc))
    else:
        if (
            isinstance(card_document, dict)
            and card_document.get("schema_version") == "tool-card-v1"
            and card_document.get("id") == result["tool"]
        ):
            report.check(True, "card: tool-card-v1 и id совпадает с манифестом")
        else:
            report.check(False, "card: tool-card-v1 и id совпадает с манифестом")

    verify_fixture_contents(fixture, report)

    if evidence is not None:
        try:
            evidence_bytes = evidence.read_bytes()
        except OSError as exc:
            report.check(False, "evidence читается", str(exc))
        else:
            evidence_digest = adm.digest_bytes(evidence_bytes)
            report.note("evidence", str(evidence))
            report.note("evidence_digest", evidence_digest)
            report.note("evidence_bytes", str(len(evidence_bytes)))
            text = evidence_bytes.decode("utf-8", "replace")
            if result["key_fingerprint"] in text:
                report.check(True, "evidence упоминает fingerprint (текстовая проверка)")
            else:
                report.warn("evidence не упоминает fingerprint (текстовая проверка)")
            manifest_digest = adm.digest_bytes(manifest_bytes)
            if manifest_digest in text:
                report.check(True, "evidence упоминает manifest_digest (текстовая проверка)")
            else:
                report.warn("evidence не упоминает manifest_digest (текстовая проверка)")

    try:
        state = rs.computed_state()
    except rs.RegistryError as exc:
        report.check(False, "production registry читается и цел", str(exc))
    else:
        report.check(True, "production registry читается и цел")
        tool = result["tool"]
        record = (state.get("tools") or {}).get(tool) or {}
        report.note(
            "production",
            f"{tool}={record.get('state')}; active={state.get('active') or '[]'}",
        )
        if tool in (state.get("active") or []):
            report.warn(
                f"production {tool} уже active",
                "повторная активация требует отдельного решения",
            )
        else:
            report.check(True, f"production {tool} не active")
    return report


def self_test() -> int:
    checks = 0
    work = Path(tempfile.mkdtemp(prefix="herness-owner-verify-")).resolve()
    try:
        key_path, anchor_path, fingerprint = adm.create_test_key(work / "keys")
        artifacts = work / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        paths = {
            "card_digest": artifacts / "card.json",
            "source_digest": artifacts / "head.rs",
            "binary_digest": artifacts / "binary",
            "fixture_digest": artifacts / "fixtures" / "manifest.json",
            "policy_digest": artifacts / "policy.json",
            "room_digest": artifacts / "room.json",
        }
        (artifacts / "fixtures").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CARD, paths["card_digest"])
        shutil.copyfile(SOURCE, paths["source_digest"])
        shutil.copyfile(SOURCE, paths["binary_digest"])
        shutil.copyfile(FIXTURES / "manifest.json", paths["fixture_digest"])
        shutil.copyfile(FIXTURES / "head-slice.txt", artifacts / "fixtures" / "head-slice.txt")
        shutil.copyfile(POLICY, paths["policy_digest"])
        shutil.copyfile(ROOM, paths["room_digest"])
        digests = {field: adm.digest_file(path) for field, path in paths.items()}
        key = adm.load_private_key(key_path)
        _public_fingerprint, _public, _min_epoch, _revoked, expected_prev = adm.load_anchor(
            anchor_path.read_bytes()
        )
        manifest_path = work / "manifest.json"
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
        for field, digest in digests.items():
            document[field] = digest
        manifest_bytes = adm.canonical(document) + b"\n"
        manifest_path.write_bytes(manifest_bytes)
        signature = adm.sign_manifest(manifest_bytes, key)
        sig_path = work / "manifest.sig"
        sig_path.write_bytes((signature + "\n").encode("ascii"))
        evidence = work / "evidence.txt"
        evidence.write_text(
            f"{MARKER}\nfingerprint {fingerprint}\nmanifest {adm.digest_bytes(manifest_bytes)}\n",
            encoding="utf-8",
        )

        now = adm.parse_time("2026-11-17T12:00:00Z", "now")
        good = verify_package(
            manifest=manifest_path,
            sig=sig_path,
            anchor=anchor_path,
            card=paths["card_digest"],
            source=paths["source_digest"],
            binary=paths["binary_digest"],
            fixture=paths["fixture_digest"],
            policy=paths["policy_digest"],
            room=paths["room_digest"],
            now_unix=now,
            allow_test_only=True,
            evidence=evidence,
        )
        checks += 1
        assert good.ok, good.text("good package")

        policy_fail = verify_package(
            manifest=manifest_path,
            sig=sig_path,
            anchor=anchor_path,
            card=paths["card_digest"],
            source=paths["source_digest"],
            binary=paths["binary_digest"],
            fixture=paths["fixture_digest"],
            policy=paths["policy_digest"],
            room=paths["room_digest"],
            now_unix=now,
            allow_test_only=False,
        )
        checks += 1
        assert not policy_fail.ok, "test_only без --allow-test-only должен провалить отчёт"

        tampered_card = work / "tampered-card.json"
        raw = paths["card_digest"].read_bytes()
        tampered_card.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        card_fail = verify_package(
            manifest=manifest_path,
            sig=sig_path,
            anchor=anchor_path,
            card=tampered_card,
            source=paths["source_digest"],
            binary=paths["binary_digest"],
            fixture=paths["fixture_digest"],
            policy=paths["policy_digest"],
            room=paths["room_digest"],
            now_unix=now,
            allow_test_only=True,
        )
        checks += 1
        assert not card_fail.ok, "изменённая карточка должна провалить отчёт"
        assert any("card_digest" in name for flag, name, _ in card_fail.checks if not flag)

        content = artifacts / "fixtures" / "head-slice.txt"
        original = content.read_bytes()
        content.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        fixture_fail = verify_package(
            manifest=manifest_path,
            sig=sig_path,
            anchor=anchor_path,
            card=paths["card_digest"],
            source=paths["source_digest"],
            binary=paths["binary_digest"],
            fixture=paths["fixture_digest"],
            policy=paths["policy_digest"],
            room=paths["room_digest"],
            now_unix=now,
            allow_test_only=True,
        )
        checks += 1
        assert not fixture_fail.ok, "изменённое содержимое фикстуры должно провалить отчёт"
        assert any("sha256 содержимого" in name for flag, name, _ in fixture_fail.checks if not flag)

        bad_sig = work / "bad.sig"
        first = "0" if signature[0] != "0" else "1"
        bad_sig.write_text(first + signature[1:] + "\n", encoding="ascii")
        sig_fail = verify_package(
            manifest=manifest_path,
            sig=bad_sig,
            anchor=anchor_path,
            card=paths["card_digest"],
            source=paths["source_digest"],
            binary=paths["binary_digest"],
            fixture=paths["fixture_digest"],
            policy=paths["policy_digest"],
            room=paths["room_digest"],
            now_unix=now,
            allow_test_only=True,
        )
        checks += 1
        assert not sig_fail.ok, "изменённая подпись должна провалить отчёт"

        print(f"PASS owner verify self-test: {checks} проверок")
        print("test-only: true; ключ эфемерный; запись не выполнялась")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="read-only проверка owner-пакета допуска")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--sig")
    parser.add_argument("--anchor")
    parser.add_argument("--card")
    parser.add_argument("--source")
    parser.add_argument("--binary")
    parser.add_argument("--fixture")
    parser.add_argument("--policy")
    parser.add_argument("--room")
    parser.add_argument("--evidence")
    parser.add_argument("--now")
    parser.add_argument("--allow-test-only", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.self_test:
        return self_test()
    required = ("manifest", "sig", "anchor", "card", "source", "binary", "fixture", "policy", "room")
    missing = [name for name in required if not getattr(args, name)]
    if missing:
        parser.error("не хватает аргументов: " + ", ".join("--" + name for name in missing))
    now_unix = (
        adm.parse_time(args.now, "now") if args.now else int(time.time())
    )
    report = verify_package(
        manifest=Path(args.manifest),
        sig=Path(args.sig),
        anchor=Path(args.anchor),
        card=Path(args.card),
        source=Path(args.source),
        binary=Path(args.binary),
        fixture=Path(args.fixture),
        policy=Path(args.policy),
        room=Path(args.room),
        now_unix=now_unix,
        allow_test_only=args.allow_test_only,
        evidence=Path(args.evidence) if args.evidence else None,
    )
    if not args.quiet:
        print(
            report.text(
                f"{MARKER}: read-only проверка пакета допуска\n"
                f"Дата: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}; "
                f"хост: {platform.platform()}; Python: {platform.python_version()}"
            )
        )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
