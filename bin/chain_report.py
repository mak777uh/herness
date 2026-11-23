"""Deterministic machine report for K9 proof-binding fixtures.

    python bin/chain_report.py --write
    python bin/chain_report.py --check

Отчёт пересчитывает subject, exact-byte artifact hash и verdict checker'а.
Он не объявляет истинность доказательства и не выдаёт K9_proven.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin import chain  # noqa: E402
from bin.lean_paths import lean_toolchain  # noqa: E402

FIXTURES = ROOT / "lab" / "fixtures" / "chain"
ARTIFACT = "proofs/Proofs/ChainInstances.lean"
OUT = ROOT / "research" / "proofs" / "k9-chain-instances.json"
EXPECTED = {
    "allowed.json": (True, []),
    "taint.json": (False, ["K9_TAINT_ESCAPE"]),
    "methods-empty.json": (False, ["K9_DOWNSTREAM_MISSING_METHOD"]),
    "methods-absent.json": (False, ["K9_SCHEMA"]),
    "methods-ok.json": (True, []),
}


def build_report() -> dict:
    artifact_path = ROOT / Path(*ARTIFACT.split("/"))
    cases = []
    for path in sorted(FIXTURES.glob("*.json")):
        if path.name not in EXPECTED:
            continue
        decl = chain.load_json(path)
        if not isinstance(decl, dict):
            raise ValueError(f"{path.name}: declaration must be an object")
        report = chain.check_chain(decl)
        codes = sorted(problem["code"] for problem in report["problems"])
        expected_ok, expected_codes = EXPECTED[path.name]
        cases.append({
            "fixture": f"lab/fixtures/chain/{path.name}",
            "subject_sha256": chain.subject_sha256(decl),
            "ok": report["ok"],
            "codes": codes,
            "expected_ok": expected_ok,
            "expected_codes": expected_codes,
            "matches_expected": report["ok"] is expected_ok and codes == expected_codes,
        })
    return {
        "schema": 1,
        "id": "K9-CHAIN-INSTANCES",
        "toolchain": lean_toolchain(),
        "proof_artifact": ARTIFACT,
        "proof_artifact_sha256": chain.digest_file(artifact_path),
        "cases": cases,
        "ok": len(cases) == len(EXPECTED) and all(case["matches_expected"] for case in cases),
        "caveat": "binding and model checks only; proof truth and downstream code are not verified",
    }


def render(report: dict) -> str:
    return chain.canonical_json(report) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="записать отслеживаемый machine report")
    mode.add_argument("--check", action="store_true", help="сверить отчёт с текущим деревом")
    args = parser.parse_args(argv)

    report = build_report()
    text = render(report)
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8", newline="\n")
    elif args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("machine report missing or stale", file=sys.stderr)
            return 1
    else:
        print(text, end="")
    if not report["ok"]:
        print("one or more fixture verdicts changed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
