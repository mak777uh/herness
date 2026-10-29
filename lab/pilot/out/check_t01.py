"""T-01-L2 answer check: the answer file exists, is valid JSON, and has the protocol shape."""
import hashlib
import json
import pathlib
import sys

path = pathlib.Path(__file__).with_name("T-01-L2.answer.json")
problems = []

if not path.is_file():
    print(f"FAIL: {path} does not exist")
    sys.exit(1)

raw = path.read_bytes()
try:
    data = json.loads(raw.decode("utf-8"))
except Exception as exc:  # noqa: BLE001
    print(f"FAIL: invalid JSON: {exc}")
    sys.exit(1)

answers = data.get("answers")
if not isinstance(answers, list) or not answers:
    problems.append("answers: missing or not a non-empty list")
    answers = []
for i, a in enumerate(answers):
    if not isinstance(a, dict):
        problems.append(f"answers[{i}]: not an object")
        continue
    for key in ("id", "answer", "bypasses"):
        if key not in a:
            problems.append(f"answers[{i}]: missing key '{key}'")
    if not isinstance(a.get("bypasses"), list):
        problems.append(f"answers[{i}].bypasses: not a list")
    if not str(a.get("answer", "")).strip():
        problems.append(f"answers[{i}].answer: empty")

nc = data.get("not_claimed")
if not isinstance(nc, list) or not nc:
    problems.append("not_claimed: missing or not a non-empty list")

print(f"file    : {path}")
print(f"bytes   : {len(raw)}")
print(f"sha256  : {hashlib.sha256(raw).hexdigest()}")
for a in answers:
    if isinstance(a, dict):
        print(f"id      : {a.get('id')}")
        print(f"bypasses: {len(a.get('bypasses') or [])}")
        print(f"not_claimed: {len(nc or [])}")

if problems:
    print("FAIL: " + "; ".join(problems))
    sys.exit(1)
print("PASS: file written, valid JSON, protocol shape ok")
