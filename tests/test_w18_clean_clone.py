"""W18: HEAD-bound clean-clone, EOL и sealed pilot baseline correction.

Финальный clean-clone запуск устанавливает W18_REQUIRE_CLEAN=1. В разработческом
дереве допускаются только явно перечисленные W18-файлы; это не выдаёт clean PASS.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bin"))

import pilot_generator as pg  # noqa: E402
import registry_state as rs  # noqa: E402
import seal as method_seal  # noqa: E402

RESULTS: list[tuple[bool, str]] = []
SOURCE_SHA256 = "42fb4a435df7798a0505e459bf315b5582c04bfd20ce76b7fcf8789d7b9c2af5"
OLD_NEW_TOOL = "sha256:cadd56ad6569165704205e5a336fe9412be61d329363810e8da4d4e2d9c5e816"
OLD_GENERATOR = "sha256:93c44b990f96705402c6a13c24f713a4f4e5a9101761d9bc72b3f32677501c5b"
CHECKOUT_SHA256 = "9b1dc65e39c0b85eecba1d3ff61967d3b135327e500a843bcbb063a0ee9caf38"
BLOB_SHA256 = "bd73f29954140ff6cc6092c8dac297d259d7726be537e5be80115fc747508979"
REGISTRY_PREFIX_SHA256 = "6fbde54f5538ff69025ee613794825b43e45f496afdb03f0a5bd71b06261f2b8"
CRLF = bytes((13, 10))
DEV_FILES = {
    ".gitattributes",
    "bin/pilot_generator.py",
    "bin/preflight.py",
    "bin/registry_state.py",
    "lab/prereg/PILOT-GENERATOR-R1-BASELINE-CORRECTION.json",
    "lab/prereg/PILOT-GENERATOR-R1-BASELINE-CORRECTION.json.sha256",
    "lab/prereg/REGISTRY-DESCRIPTION-APPENDONLY-R1.json",
    "lab/prereg/REGISTRY-DESCRIPTION-APPENDONLY-R1.json.sha256",
    "lab/prereg/W18-CLEAN-CLONE-R1.json",
    "lab/prereg/W03-REVIEW3-SUCCESSOR-BASELINE-R1.json",
    "lab/prereg/W03-REVIEW3-SUCCESSOR-BASELINE-R1.json.sha256",
    "lab/prereg/W18-CLEAN-CLONE-R1.json.sha256",
    "lab/registry.json",
    "lab/tools/registry.events.jsonl",
    "lab/tools/registry.state.json",
    "runs/exp-w18-clean-clone-r1/baseline-red.txt",
    "tests/test_list_contract.py",
    "tests/test_registry_state.py",
    "tests/test_w03_lifecycle_review3.py",
    "tests/test_w18_clean_clone.py",
    "tests/test-manifest.json",
}


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def run_python(path: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, path], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=180,
    )


def source_document() -> dict:
    return json.loads(pg.PREREG.read_text(encoding="utf-8"))


def correction_document() -> dict:
    correction, problems = pg.load_correction()
    if problems:
        raise AssertionError(problems)
    assert correction is not None
    return correction


def main() -> int:
    # 1. Исходный sealed prereg и исторические digests не переписаны.
    raw = pg.PREREG.read_bytes()
    source = source_document()
    check(
        hashlib.sha256(raw).hexdigest() == SOURCE_SHA256
        and source["frozen"]["new_tool_digest"] == OLD_NEW_TOOL
        and source["frozen"]["files"]["bin/pilot_generator.py"] == OLD_GENERATOR,
        "исходный PILOT-GENERATOR-R1 и historical digests сохранены",
    )

    # 2. Checkout representation закреплена и совпадает с Review3 baseline.
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    checkout = (ROOT / "core-rs/src/loopmod.rs").read_bytes()
    check(
        "core-rs/src/loopmod.rs text eol=crlf" in attributes
        and len(checkout) == 198631
        and checkout.count(CRLF) == 3821
        and hashlib.sha256(checkout).hexdigest() == CHECKOUT_SHA256,
        "loopmod checkout: CRLF pin, 198631 байт, 3821 CRLF, SHA-256 9b1dc65e…",
    )

    # 3. Git blob измеряется отдельно и намеренно отличается от checkout.
    blob_proc = subprocess.run(
        ["git", "show", "HEAD:core-rs/src/loopmod.rs"], cwd=ROOT,
        capture_output=True, check=True, timeout=30,
    )
    blob = blob_proc.stdout
    check(
        len(blob) == 194810 and blob.count(CRLF) == 0
        and hashlib.sha256(blob).hexdigest() == BLOB_SHA256
        and blob != checkout,
        "loopmod Git blob: LF, 194810 байт, SHA-256 bd73f299…, blob≠checkout",
    )

    # 4. Положительный контроль correction.
    check(pg.verify_prereg(source) == [], "pilot --verify принимает текущую sealed correction")

    # 5. Missing correction fail-closed.
    source_digest = pg.file_digest(pg.PREREG)
    check(
        bool(pg.validate_correction(source, None, source_digest)),
        "missing correction отвергнута",
    )

    # 6. Tampered correction при неизменном sidecar fail-closed.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / pg.CORRECTION.name
        target.write_bytes(pg.CORRECTION.read_bytes())
        method_seal.sidecar(target).write_bytes(method_seal.sidecar(pg.CORRECTION).read_bytes())
        tampered = json.loads(target.read_text(encoding="utf-8"))
        tampered["tampered"] = True
        target.write_text(json.dumps(tampered, ensure_ascii=False, indent=1), encoding="utf-8")
        sealed, _message = method_seal.verify(target)
    check(not sealed, "tampered correction отвергнута sidecar")

    # 7. Correction не может подменить source prereg digest.
    wrong_source = copy.deepcopy(correction_document())
    wrong_source["source_prereg_sha256"] = "sha256:" + "0" * 64
    check(
        bool(pg.verify_documents(source, wrong_source, source_digest)),
        "wrong source digest отвергнут",
    )

    # 8. Correction не может принять другой new_tool/generator digest.
    wrong_digests = copy.deepcopy(correction_document())
    wrong_digests["corrected_frozen"]["new_tool_digest"] = "sha256:" + "0" * 64
    wrong_digests["corrected_frozen"]["files"]["bin/new_tool.py"] = "sha256:" + "0" * 64
    wrong_digests["corrected_frozen"]["files"]["bin/pilot_generator.py"] = "sha256:" + "1" * 64
    check(
        bool(pg.verify_documents(source, wrong_digests, source_digest)),
        "wrong corrected new_tool/generator digests отвергнуты",
    )

    # 9. Посторонний файл и threshold mutation не разрешены correction.
    foreign = copy.deepcopy(correction_document())
    foreign["corrected_frozen"]["files"]["lab/pilot/mutants.json"] = "sha256:" + "2" * 64
    foreign_thresholds = copy.deepcopy(correction_document())
    foreign_thresholds["thresholds_sha256"] = "sha256:" + "3" * 64
    check(
        bool(pg.verify_documents(source, foreign, source_digest))
        and bool(pg.verify_documents(source, foreign_thresholds, source_digest)),
        "foreign path и threshold mutation отвергнуты",
    )

    # 10. Append-only prefix seq=0..8 неизменён; seq=9 ведёт на canonical card.
    event_bytes = (ROOT / "lab/tools/registry.events.jsonl").read_bytes()
    prefix = b"".join(event_bytes.splitlines(keepends=True)[:9])
    events = rs.read_events()
    state = rs.computed_state()
    check(
        hashlib.sha256(prefix).hexdigest() == REGISTRY_PREFIX_SHA256
        and len(events) >= 10 and events[9][1]["seq"] == 9
        and events[9][1]["type"] == "candidate"
        and events[9][1]["body"].get("admission") is None
        and events[9][1]["body"].get("card") == "lab/tools/cards/head.json"
        and all(event[1].get("tool_id") != "head" for event in events[10:])
        and state["active"] == [] and state["tools"]["head"]["seq"] == 9
        and state["tools"]["head"]["card"] == "lab/tools/cards/head.json"
        and rs.check_files() == [],
        "registry: seq=0..8 неизменны, seq=9 canonical candidate, later events не меняют head, active=[]",
    )

    # 11. V1/V6 proof-binding corpus и exact LF bytes proof artifact.
    proof = (ROOT / "proofs/Proofs/ChainInstances.lean").read_bytes()
    chain = run_python("tests/test_chain.py")
    check(
        chain.returncode == 0 and "провалов: 0" in chain.stdout
        and "proofs/Proofs/ChainInstances.lean text eol=lf" in attributes
        and len(proof) == 2478 and proof.count(CRLF) == 0
        and hashlib.sha256(proof).hexdigest() == "8cfe7c4de849e80e93712eb59de486d20c39c43e18aae49db38934e118a03308",
        f"V1/V6 chain и proof exact bytes: 0 провалов (rc={chain.returncode})",
    )

    # 12. V4 canonical/legacy/schema/no-auto-conversion corpus.
    v4 = [run_python(path) for path in (
        "tests/test_head_cards.py", "tests/test_tool_card.py", "tests/test_card_atoms.py",
    )]
    check(all(item.returncode == 0 for item in v4),
          "V4 head/tool-card/card-atoms: 0 провалов")

    # 13. W03 Review3 остаётся 9/9 на закреплённом checkout.
    review3 = run_python("tests/test_w03_lifecycle_review3.py")
    check(review3.returncode == 0 and "9/9 ok" in review3.stdout,
          f"W03 Review3: 9/9 (rc={review3.returncode})")

    # 14. Финальный clean clone обязан иметь пустой worktree. Development run
    # допускает только явный W18 scope и не считается clean-clone PASS.
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=True, timeout=30,
    ).stdout.splitlines()
    require_clean = os.environ.get("W18_REQUIRE_CLEAN") == "1"
    if require_clean:
        check(status == [], f"clean worktree: пусто (HEAD={subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()})")
    else:
        paths = {line[3:] for line in status}
        check(paths <= DEV_FILES, f"development worktree ограничен W18 scope: {sorted(paths - DEV_FILES)}")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _message in RESULTS if not flag)
    mode = "clean-clone" if require_clean else "development-scope"
    print(f"W18 controls: {len(RESULTS) - failed}/{len(RESULTS)} ok; провалов: {failed}; mode={mode}")
    return 1 if failed or len(RESULTS) != 14 else 0


if __name__ == "__main__":
    raise SystemExit(main())
