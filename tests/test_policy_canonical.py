"""E-0088: canonical policy loader без fallback, overwrite и cross-root подмены.

Запуск: python tests/test_policy_canonical.py
Windows и POSIX: 15/15 без N/A. Секреты и сеть не используются.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import policy  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def synthetic_policy(marker: str, tool: str = "alpha") -> dict:
    return {
        "version": 1,
        "principle": marker,
        "rules": [{
            "id": f"{tool}-allow",
            "tool": tool,
            "subject": "agent",
            "action": "read",
            "resource": "file:/mnt/**",
            "effect": "allow",
            "level": "A",
            "why": "synthetic policy fixture",
        }],
        "delegation": [],
    }


def write_policy(root: Path, data: dict | str) -> Path:
    path = root / "lab" / "tools" / "policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8", newline="\n")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
    return path


def expect_policy_error(root: Path, fragment: str, message: str) -> None:
    error_type = getattr(policy, "PolicyDataError", None)
    try:
        policy.load(root)
    except Exception as exc:  # noqa: BLE001 — отсутствие единого типа тоже RED
        check(error_type is not None and isinstance(exc, error_type) and fragment in str(exc),
              message)
        return
    check(False, message)


def run_cli(script: Path, root: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def test_canonical_policy_loads_23_rules() -> None:
    data = policy.load()
    check(isinstance(data, dict) and len(data.get("rules", [])) == 23,
          "canonical policy загружается и содержит 23 rules")


def test_canonical_policy_passes_semantic_check() -> None:
    check(policy.check(policy.load()) == [],
          "canonical policy проходит существующие semantic checks")


def test_missing_canonical_is_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        expect_policy_error(Path(tmp), "missing canonical policy",
                            "missing canonical даёт PolicyDataError, а не fallback")


def test_malformed_json_is_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_policy(root, "{")
        expect_policy_error(root, "malformed canonical policy",
                            "malformed JSON даёт единый PolicyDataError")


def test_empty_rules_are_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = synthetic_policy("empty")
        data["rules"] = []
        write_policy(root, data)
        expect_policy_error(root, "empty canonical policy",
                            "пустой rules отвергается до check/show")


def test_malformed_rule_is_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = synthetic_policy("malformed-rule")
        del data["rules"][0]["tool"]
        write_policy(root, data)
        expect_policy_error(root, "invalid canonical policy",
                            "rule без обязательного tool отвергается структурно")


def test_duplicate_rule_id_is_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = synthetic_policy("duplicate")
        data["rules"].append(dict(data["rules"][0]))
        write_policy(root, data)
        expect_policy_error(root, "invalid canonical policy",
                            "duplicate rule id отвергается")


def test_unknown_effect_is_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = synthetic_policy("unknown-effect")
        data["rules"][0]["effect"] = "maybe"
        write_policy(root, data)
        expect_policy_error(root, "invalid canonical policy",
                            "unknown effect отвергается как неизвестный класс")


def test_unknown_level_is_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = synthetic_policy("unknown-level")
        data["rules"][0]["level"] = "Z"
        write_policy(root, data)
        expect_policy_error(root, "invalid canonical policy",
                            "unknown level отвергается как неизвестный класс")


def test_dual_root_does_not_cross_contaminate() -> None:
    with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
        root_left, root_right = Path(left), Path(right)
        write_policy(root_left, synthetic_policy("LEFT", "alpha"))
        write_policy(root_right, synthetic_policy("RIGHT", "beta"))
        first = policy.load(root_left)
        second = policy.load(root_right)
        again = policy.load(root_left)
        check(first["principle"] == "LEFT" and first["rules"][0]["tool"] == "alpha"
              and second["principle"] == "RIGHT" and second["rules"][0]["tool"] == "beta"
              and again["principle"] == "LEFT",
              "два root не подменяют друг друга и повторный load не cached")


def test_build_flag_is_rejected_without_write() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = root / "bin" / "policy.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "bin" / "policy.py", script)
        path = write_policy(root, '{"sentinel": true}\n')
        before = path.read_bytes()
        result = run_cli(script, root, "--build")
        check(result.returncode == 2 and path.read_bytes() == before,
              "--build отвергнут rc=2 и canonical bytes не изменены")


def test_check_cli_missing_is_clean_nonzero() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = root / "bin" / "policy.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "bin" / "policy.py", script)
        result = run_cli(script, root, "--check")
        text = result.stdout + result.stderr
        check(result.returncode != 0 and "Traceback" not in text
              and "missing canonical policy" in text,
              "CLI --check на missing policy даёт чистый nonzero без traceback")


def test_show_cli_uses_explicit_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_policy(root, synthetic_policy("EXPLICIT_ROOT", "alpha"))
        result = run_cli(ROOT / "bin" / "policy.py", root, "--root", str(root), "--show", "alpha")
        check(result.returncode == 0 and "EXPLICIT_ROOT" in result.stdout
              and "alpha" in result.stdout,
              "CLI --show читает явно переданный root")


def test_check_cli_valid_reports_23() -> None:
    result = run_cli(ROOT / "bin" / "policy.py", ROOT, "--root", str(ROOT), "--check")
    check(result.returncode == 0 and "23 правил" in result.stdout,
          "CLI --check на canonical root сообщает 23 rules и rc=0")


def test_embedded_fallback_is_absent() -> None:
    check(not hasattr(policy, "POLICY_DATA"),
          "embedded POLICY_DATA удалён, второго source of truth нет")


def main() -> int:
    tests = (
        test_canonical_policy_loads_23_rules,
        test_canonical_policy_passes_semantic_check,
        test_missing_canonical_is_fail_closed,
        test_malformed_json_is_fail_closed,
        test_empty_rules_are_fail_closed,
        test_malformed_rule_is_fail_closed,
        test_duplicate_rule_id_is_fail_closed,
        test_unknown_effect_is_fail_closed,
        test_unknown_level_is_fail_closed,
        test_dual_root_does_not_cross_contaminate,
        test_build_flag_is_rejected_without_write,
        test_check_cli_missing_is_clean_nonzero,
        test_show_cli_uses_explicit_root,
        test_check_cli_valid_reports_23,
        test_embedded_fallback_is_absent,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 — любая неожиданная ошибка тоже RED
            check(False, f"{test.__name__}: {type(exc).__name__}: {exc}")
    failed_count = 0
    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
        failed_count += 0 if flag else 1
    print(f"проверок: {len(RESULTS)}; провалов: {failed_count}")
    return 0 if failed_count == 0 and len(RESULTS) == 15 else 1


if __name__ == "__main__":
    raise SystemExit(main())
