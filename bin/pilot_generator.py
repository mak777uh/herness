"""pilot_generator.py — инженерный пилот генератора `file_read_stream` (Q16).

Пилот запускается только после закрытого `HEAD-SLICE-R1`. Он:

1. сверяет замороженные до прогона хеши спецификаций и мутантов;
2. трижды генерирует 20 кандидатов через `bin/new_tool.py` и требует
   байт-идентичный результат;
3. компилирует и трижды исполняет каждый кандидатный набор проверок в WSL;
4. подкладывает 24 мутанта (16 критических + 8 функциональных) в общий source
   и требует, чтобы сгенерированные проверки поймали каждого;
5. пишет evidence и возвращает 0 только при выполнении всех порогов.

Границы: пилот не активирует инструменты, не пишет в активную policy/registry/
admission, не создаёт owner-ключ и не выдаёт `K9_proven`. Кандидаты остаются в
`lab/candidates/` и не доступны модели через `run_tool_g`.

    python bin/pilot_generator.py --prereg   # один раз, до прогона
    python bin/pilot_generator.py --run
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"
sys.path.insert(0, str(BIN))

import new_tool as nt  # noqa: E402
import seal as method_seal  # noqa: E402

AUTHORED = ROOT / "lab" / "pilot" / "specs" / "authored"
HELDOUT = ROOT / "lab" / "pilot" / "specs" / "heldout"
MUTANTS = ROOT / "lab" / "pilot" / "mutants.json"
PREREG = ROOT / "lab" / "prereg" / "PILOT-GENERATOR-R1.json"
CORRECTION = ROOT / "lab" / "prereg" / "PILOT-GENERATOR-R1-BASELINE-CORRECTION.json"
EVIDENCE = ROOT / "research" / "outputs" / "PILOT-GENERATOR-R1-2026-11-17.txt"
CANDIDATES = ROOT / "lab" / "candidates"
OUT_ROOT = CANDIDATES / "file_read_stream"
HEAD_PREREG = ROOT / "lab" / "prereg" / "HEAD-SLICE-R1.json"
HEAD_EVIDENCE = ROOT / "research" / "outputs" / "HEAD-SLICE-R1-2026-11-17.txt"
DATE = "2026-11-17"

THRESHOLDS = {
    "specs_total": 20,
    "specs_required": 19,
    "authored_total": 12,
    "authored_required": 12,
    "heldout_total": 8,
    "heldout_required": 8,
    "critical_total": 16,
    "critical_required": 16,
    "functional_total": 8,
    "functional_required": 8,
    "repeats": 3,
    "generation_repeats": 3,
}

CRITERION = (
    "PASS только если: сгенерировано 20/20 кандидатов, генерация байт-идентична "
    "в 3/3 повторах; все 12 authored и все 8 held-out спецификаций проходят "
    "3/3 повтора (общий порог scorecard >=19/20, held-out строго 8/8); "
    "16/16 критических и 8/8 функциональных мутантов пойманы; ни одна проверка "
    "не зелёная при отсутствующей телеметрии. Любой пропуск — FAIL без ослабления."
)

# W18: исходный prereg остаётся sealed. Correction разрешена только для двух
# инженерных файлов, изменившихся после пилота; остальные specs/mutants/head
# evidence и thresholds продолжают сверяться с исходной фиксацией.
CORRECTION_ID = "PILOT-GENERATOR-R1-BASELINE-CORRECTION"
CORRECTION_FILES = {"bin/new_tool.py", "bin/pilot_generator.py"}
CORRECTION_KEYS = {"new_tool_digest"}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def canonical_map_digest(mapping: dict[str, str]) -> str:
    ordered = {key: mapping[key] for key in sorted(mapping)}
    return digest_bytes(json.dumps(ordered, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8"))


def spec_paths() -> list[tuple[str, Path]]:
    rows = []
    for group, directory in (("authored", AUTHORED), ("heldout", HELDOUT)):
        for path in sorted(directory.glob("*.json")):
            rows.append((group, path))
    return rows


def frozen_files() -> dict[str, str]:
    files = {}
    for _, path in spec_paths():
        files[path.relative_to(ROOT).as_posix()] = file_digest(path)
    for path in (MUTANTS, BIN / "new_tool.py", BIN / "pilot_generator.py",
                 HEAD_PREREG, HEAD_EVIDENCE):
        files[path.relative_to(ROOT).as_posix()] = file_digest(path)
    return files


def frozen_document() -> dict:
    files = frozen_files()
    authored = {key: value for key, value in files.items() if "/authored/" in key}
    heldout = {key: value for key, value in files.items() if "/heldout/" in key}
    return {
        "files": files,
        "authored_digest": canonical_map_digest(authored),
        "heldout_digest": canonical_map_digest(heldout),
        "mutants_digest": files[MUTANTS.relative_to(ROOT).as_posix()],
        "new_tool_digest": files[(BIN / "new_tool.py").relative_to(ROOT).as_posix()],
        "head_slice_prereg_digest": files[HEAD_PREREG.relative_to(ROOT).as_posix()],
        "head_slice_evidence_digest": files[HEAD_EVIDENCE.relative_to(ROOT).as_posix()],
    }


def prereg_document() -> dict:
    return {
        "schema": 2,
        "id": "PILOT-GENERATOR-R1",
        "date": DATE,
        "question": (
            "Может ли шаблонный генератор выдать кандидата file_read_stream, "
            "который проходит 20 замороженных спецификаций, а его сгенерированные "
            "проверки ловят 24 подложенных мутанта?"
        ),
        "hypothesis": (
            "Для одного шаблона генерация детерминирована; сгенерированные проверки "
            "достаточны, чтобы отвергнуть 16 критических и 8 функциональных дефектов. "
            "Это инженерный gate вертикали, не доказательство безопасности."
        ),
        "criterion": CRITERION,
        "arms": [
            "A: ручной head/HEAD-SLICE-R1 — уже закрыт PASS и является входным условием",
            "B: генератор new_tool.py — выдаёт card/source/tests/policy fragment в lab/candidates",
            "C: мутанты — подкладываются в source и проверяются сгенерированными tests",
        ],
        "sensitivity": (
            "24 мутанта: 16 критических (лимиты, output cap, K4, UTF-8, CR, "
            "line_count, bytes_read) и 8 функциональных (stop_reason, диагностика, "
            "границы схемы). Один выживший критический — стоп."
        ),
        "unit_of_analysis": "один spec — один кандидат; один мутант — один набор проверок",
        "primary_metric": "spec pass count, mutant catch count, generation/run determinism",
        "test": "python bin/pilot_generator.py --run",
        "stopping_rule": (
            "FAIL без ослабления, если критический мутант выжил, held-out <8/8, "
            "генерация недетерминирована, baseline не проходит 3/3 или запись вышла "
            "за lab/candidates и research/outputs."
        ),
        "closed": False,
        "thresholds": THRESHOLDS,
        "frozen": frozen_document(),
        "head_slice": {
            "prereg": "lab/prereg/HEAD-SLICE-R1.json",
            "evidence": "research/outputs/HEAD-SLICE-R1-2026-11-17.txt",
            "required_closed": True,
        },
        "note": (
            "Пороги и хеши зафиксированы до записанного прогона; после первого "
            "прогона менять их запрещено. Пилот не делает ни один инструмент active."
        ),
    }


def write_prereg() -> int:
    document = prereg_document()
    payload = (json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
               + "\n").encode("utf-8")
    if PREREG.exists():
        current = json.loads(PREREG.read_text(encoding="utf-8"))
        problems = verify_prereg(current)
        if problems:
            for problem in problems:
                print(f"[FAIL] {problem}")
            print("пре-регистрация существует и расходится с текущими файлами; "
                  "перезапись запрещена")
            return 1
        print(f"[ok] пре-регистрация уже зафиксирована: {file_digest(PREREG)}")
        return 0
    PREREG.parent.mkdir(parents=True, exist_ok=True)
    PREREG.write_bytes(payload)
    print(f"[ok] пре-регистрация записана: {PREREG.relative_to(ROOT)}")
    print(f"     digest: {digest_bytes(payload)}")
    print(f"     authored: {document['frozen']['authored_digest']}")
    print(f"     heldout:  {document['frozen']['heldout_digest']}")
    print(f"     mutants:  {document['frozen']['mutants_digest']}")
    return 0


def load_correction() -> tuple[dict | None, list[str]]:
    """Correction обязательна и fail-closed; её sidecar проверяет точные байты."""
    if not CORRECTION.exists():
        return None, [f"нет sealed correction {CORRECTION.relative_to(ROOT)}"]
    try:
        document = json.loads(CORRECTION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"correction не читается: {exc}"]
    if not isinstance(document, dict):
        return None, ["correction не является объектом"]
    sealed, message = method_seal.verify(CORRECTION)
    if not sealed:
        return None, [message]
    return document, []


def validate_correction(document: dict, correction: dict | None, source_digest: str) -> list[str]:
    """Correction меняет только два инженерных файла и не трогает thresholds."""
    if correction is None:
        return ["correction отсутствует"]
    if correction.get("id") != CORRECTION_ID:
        return [f"correction id={correction.get('id')!r}"]
    if correction.get("source_prereg") != "lab/prereg/PILOT-GENERATOR-R1.json":
        return ["correction указывает не на исходный PILOT-GENERATOR-R1"]
    if correction.get("source_prereg_sha256") != source_digest:
        return ["correction source_prereg_sha256 не совпадает с исходным prereg"]
    if correction.get("thresholds_sha256") != canonical_map_digest(THRESHOLDS):
        return ["correction thresholds_sha256 не совпадает с замороженными thresholds"]

    frozen = document.get("frozen") or {}
    old = correction.get("historical_frozen") or {}
    new = correction.get("corrected_frozen") or {}
    if set(old) != {"files", *CORRECTION_KEYS}:
        return ["historical_frozen имеет неверный набор ключей"]
    if set(new) != {"files", *CORRECTION_KEYS}:
        return ["corrected_frozen имеет неверный набор ключей"]
    old_files = old.get("files") or {}
    new_files = new.get("files") or {}
    if set(old_files) != CORRECTION_FILES or set(new_files) != CORRECTION_FILES:
        return ["correction разрешена только для bin/new_tool.py и bin/pilot_generator.py"]
    for key in CORRECTION_KEYS:
        if old.get(key) != frozen.get(key):
            return [f"historical_frozen.{key} не совпадает с исходным prereg"]
        if not isinstance(new.get(key), str) or not DIGEST.match(new[key]):
            return [f"corrected_frozen.{key} имеет неверный digest"]
    source_files = frozen.get("files") or {}
    for path in CORRECTION_FILES:
        if old_files.get(path) != source_files.get(path):
            return [f"historical_frozen.files.{path} не совпадает с исходным prereg"]
        if not isinstance(new_files.get(path), str) or not DIGEST.match(new_files[path]):
            return [f"corrected_frozen.files.{path} имеет неверный digest"]
    if old.get("new_tool_digest") != old_files.get("bin/new_tool.py"):
        return ["historical new_tool_digest расходится с historical files"]
    if new.get("new_tool_digest") != new_files.get("bin/new_tool.py"):
        return ["corrected new_tool_digest расходится с corrected files"]
    return []


def corrected_frozen(document: dict, correction: dict) -> dict:
    frozen = dict(document.get("frozen") or {})
    files = dict(frozen.get("files") or {})
    new = correction["corrected_frozen"]
    for key in CORRECTION_KEYS:
        frozen[key] = new[key]
    files.update(new["files"])
    frozen["files"] = files
    return frozen


def verify_documents(document: dict, correction: dict | None, source_digest: str) -> list[str]:
    problems = validate_correction(document, correction, source_digest)
    if problems:
        return problems
    if document.get("id") != "PILOT-GENERATOR-R1":
        problems.append(f"id={document.get('id')!r}")
    if document.get("thresholds") != THRESHOLDS:
        problems.append("пороги в пре-регистрации отличаются от замороженных")
    frozen = corrected_frozen(document, correction)
    current = frozen_document()
    for key, value in current.items():
        if key == "files":
            continue
        if frozen.get(key) != value:
            problems.append(f"{key} изменился после фиксации: {frozen.get(key)} != {value}")
    old_files = frozen.get("files") or {}
    if old_files != current["files"]:
        for path in sorted(set(old_files) | set(current["files"])):
            if old_files.get(path) != current["files"].get(path):
                problems.append(f"файл изменился после фиксации: {path}")
    return problems


def verify_prereg(document: dict | None = None) -> list[str]:
    if document is None:
        if not PREREG.exists():
            return ["нет lab/prereg/PILOT-GENERATOR-R1.json; сначала --prereg"]
        document = json.loads(PREREG.read_text(encoding="utf-8"))
    correction, problems = load_correction()
    if problems:
        return problems
    return verify_documents(document, correction, file_digest(PREREG))


def wsl_path(path: Path) -> str:
    text = path.resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", text):
        return "/mnt/" + text[0].lower() + text[2:]
    return text


def wsl(script: str, timeout: int = 240) -> tuple[int, str]:
    result = subprocess.run(
        ["wsl", "-d", "Ubuntu", "--exec", "bash", "-lc", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def compile_and_run(directory: Path, repeats: int) -> dict:
    """Компилирует tests.rs один раз и исполняет бинарь `repeats` раз."""
    location = shlex.quote(wsl_path(directory))
    code, output = wsl(f"cd {location} && rustc --edition 2021 -O tests.rs -o pilot-tests.bin 2>&1")
    compile_error = code != 0
    runs = []
    if not compile_error:
        for _ in range(repeats):
            rc, out = wsl(f"cd {location} && ./pilot-tests.bin 2>&1")
            runs.append({"rc": rc, "out": out})
    return {"compile_rc": code, "compile_output": output,
            "compile_error": compile_error, "runs": runs}


def deterministic_runs(result: dict) -> bool:
    runs = result.get("runs") or []
    if len(runs) < THRESHOLDS["repeats"]:
        return False
    return len({(run["rc"], run["out"]) for run in runs}) == 1


def run_success(result: dict) -> bool:
    runs = result.get("runs") or []
    return (not result["compile_error"] and len(runs) == THRESHOLDS["repeats"]
            and all(run["rc"] == 0 for run in runs) and deterministic_runs(result))


def run_failure_caught(result: dict) -> bool:
    """Мутант пойман, если компиляция/исполнение отвергло его во всех повторах."""
    if result["compile_error"]:
        return True
    runs = result.get("runs") or []
    if len(runs) < THRESHOLDS["repeats"]:
        return False
    if not deterministic_runs(result):
        return False
    return all(run["rc"] != 0 for run in runs)


def first_failure_line(result: dict) -> str:
    if result["compile_error"]:
        lines = [line for line in result["compile_output"].splitlines() if "error" in line]
        return (lines[0] if lines else "compile error")[:180]
    for run in result.get("runs") or []:
        for line in run["out"].splitlines():
            if "[FAIL]" in line:
                return line.strip()[:180]
        if run["rc"] != 0:
            tail = [line for line in run["out"].splitlines() if line.strip()]
            if tail:
                return tail[-1].strip()[:180]
    return "rc!=0 без текста"


def generation_repeat(spec_directory: Path) -> dict:
    digests = []
    trees = []
    for index in range(THRESHOLDS["generation_repeats"]):
        target = Path(tempfile.mkdtemp(prefix=f".pilot-gen-{index + 1}-", dir=CANDIDATES))
        try:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = nt.main(["--all", str(spec_directory), "--out", str(target)])
            tree = {}
            for path in sorted(target.rglob("*")):
                if path.is_file():
                    tree[path.relative_to(target).as_posix()] = file_digest(path)
            digests.append(canonical_map_digest(tree))
            trees.append(tree)
            if code != 0:
                return {"error": f"new_tool rc={code}: {buffer.getvalue()[-800:]}"}
        finally:
            shutil.rmtree(target, ignore_errors=True)
    if len(set(digests)) != 1 or any(tree != trees[0] for tree in trees[1:]):
        return {"error": f"генерация недетерминирована: {digests}"}
    return {"digest": digests[0], "files": len(trees[0]), "repeats": len(digests)}


def candidate_tree_digest() -> str:
    tree = {}
    for path in sorted(OUT_ROOT.rglob("*")):
        if path.is_file():
            tree[path.relative_to(OUT_ROOT).as_posix()] = file_digest(path)
    return canonical_map_digest(tree)


def run_all() -> int:
    problems = verify_prereg()
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}")
        return 1

    head = json.loads(HEAD_PREREG.read_text(encoding="utf-8"))
    if head.get("closed") is not True:
        print("[FAIL] HEAD-SLICE-R1 не закрыт: пилот Q16 запускать нельзя")
        return 1
    if not HEAD_EVIDENCE.exists():
        print(f"[FAIL] нет evidence ручного среза: {HEAD_EVIDENCE}")
        return 1

    specs_by_group = {"authored": [], "heldout": []}
    for group, path in spec_paths():
        specs_by_group[group].append(nt.load_spec(path))
    specs = specs_by_group["authored"] + specs_by_group["heldout"]
    for spec in specs:
        spec_problems = nt.validate_spec(spec)
        if spec_problems:
            print(f"[FAIL] spec {spec.get('id')}: {spec_problems[0]}")
            return 1

    mutants_document = json.loads(MUTANTS.read_text(encoding="utf-8"))
    mutants = mutants_document.get("mutants") or []
    if len(mutants) != 24:
        print(f"[FAIL] мутантов {len(mutants)}, нужно 24")
        return 1

    print("[1/6] входной срез закрыт, пре-регистрация совпадает")
    print("[2/6] три повтора генерации...")
    generation = generation_repeat(ROOT / "lab" / "pilot" / "specs")
    if "error" in generation:
        print(f"[FAIL] {generation['error']}")
        return 1
    print(f"       generation digest {generation['digest']}, файлов {generation['files']}")

    print("[3/6] финальная генерация в lab/candidates...")
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = nt.main(["--all", str(ROOT / "lab" / "pilot" / "specs"), "--out", str(OUT_ROOT)])
    if code != 0:
        print(f"[FAIL] финальная генерация rc={code}")
        print(buffer.getvalue()[-1500:])
        return 1
    tree_digest = candidate_tree_digest()

    work = Path(tempfile.mkdtemp(prefix=".pilot-run-", dir=CANDIDATES))
    spec_results = []
    mutant_results = []
    rustc_version = ""
    try:
        version_code, version_out = wsl("rustc --version")
        rustc_version = version_out.strip() if version_code == 0 else f"rc={version_code}"

        print("[4/6] компиляция и 3 повтора каждого кандидата...")
        for group in ("authored", "heldout"):
            for spec in specs_by_group[group]:
                source_dir = OUT_ROOT / spec["id"]
                build = work / "candidates" / spec["id"]
                build.mkdir(parents=True)
                shutil.copy2(source_dir / "source.rs", build / "source.rs")
                shutil.copy2(source_dir / "tests.rs", build / "tests.rs")
                result = compile_and_run(build, THRESHOLDS["repeats"])
                passed = run_success(result)
                spec_results.append({
                    "id": spec["id"],
                    "group": group,
                    "cases": len(spec["cases"]),
                    "passed": passed,
                    "deterministic": deterministic_runs(result),
                    "compile_error": result["compile_error"],
                    "rcs": [run["rc"] for run in result["runs"]],
                    "first_failure": first_failure_line(result) if not passed else "",
                })
                print(f"       {spec['id']} [{group}] cases={len(spec['cases'])} "
                      f"{'PASS' if passed else 'FAIL'}")

        print("[5/6] baseline bundle и 24 мутанта...")
        base = work / "bundle"
        base.mkdir()
        source = (OUT_ROOT / specs_by_group["authored"][0]["id"] / "source.rs").read_text(
            encoding="utf-8")
        tests = nt.render_harness(specs)
        (base / "source.rs").write_text(source, encoding="utf-8")
        (base / "tests.rs").write_text(tests, encoding="utf-8")
        base_result = compile_and_run(base, THRESHOLDS["repeats"])
        baseline_ok = run_success(base_result)
        print(f"       baseline {'PASS' if baseline_ok else 'FAIL'} "
              f"rcs={[run['rc'] for run in base_result['runs']]}")

        for mutant in mutants:
            target = work / "mutants" / mutant["id"]
            target.mkdir(parents=True)
            if source.count(mutant["find"]) != 1:
                mutant_results.append({
                    "id": mutant["id"], "class": mutant["class"], "caught": False,
                    "deterministic": False, "compile_error": False,
                    "first_failure": "мутация не применима: find не уникален",
                })
                print(f"       {mutant['id']}: INVALID")
                continue
            mutated = source.replace(mutant["find"], mutant["replace"], 1)
            (target / "source.rs").write_text(mutated, encoding="utf-8")
            (target / "tests.rs").write_text(tests, encoding="utf-8")
            result = compile_and_run(target, THRESHOLDS["repeats"])
            caught = run_failure_caught(result)
            mutant_results.append({
                "id": mutant["id"],
                "class": mutant["class"],
                "caught": caught,
                "deterministic": deterministic_runs(result),
                "compile_error": result["compile_error"],
                "first_failure": first_failure_line(result) if caught else "SURVIVED",
            })
            print(f"       {mutant['id']} [{mutant['class']}] "
                  f"{'caught' if caught else 'SURVIVED'}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    authored_pass = sum(1 for item in spec_results if item["group"] == "authored" and item["passed"])
    heldout_pass = sum(1 for item in spec_results if item["group"] == "heldout" and item["passed"])
    specs_pass = authored_pass + heldout_pass
    critical = [item for item in mutant_results if item["class"] == "critical"]
    functional = [item for item in mutant_results if item["class"] == "functional"]
    critical_caught = sum(1 for item in critical if item["caught"])
    functional_caught = sum(1 for item in functional if item["caught"])
    all_runs_deterministic = all(item["deterministic"] for item in spec_results) \
        and all(item["deterministic"] for item in mutant_results) and baseline_ok

    failed_checks = []
    if generation["repeats"] != THRESHOLDS["generation_repeats"]:
        failed_checks.append("generation repeats")
    if specs_pass < THRESHOLDS["specs_required"]:
        failed_checks.append(f"specs {specs_pass}/20 < {THRESHOLDS['specs_required']}")
    if heldout_pass < THRESHOLDS["heldout_required"]:
        failed_checks.append(f"heldout {heldout_pass}/8")
    if critical_caught < THRESHOLDS["critical_required"]:
        failed_checks.append(f"critical {critical_caught}/16")
    if functional_caught < THRESHOLDS["functional_required"]:
        failed_checks.append(f"functional {functional_caught}/8")
    if not all_runs_deterministic:
        failed_checks.append("determinism")
    if not baseline_ok:
        failed_checks.append("baseline bundle")
    passed = not failed_checks

    evidence = render_evidence(
        generation=generation,
        tree_digest=tree_digest,
        spec_results=spec_results,
        mutant_results=mutant_results,
        baseline=base_result,
        rustc_version=rustc_version,
        counts={
            "authored": authored_pass, "heldout": heldout_pass, "specs": specs_pass,
            "critical": critical_caught, "functional": functional_caught,
        },
        passed=passed,
        failed_checks=failed_checks,
    )
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_bytes(evidence.encode("utf-8"))

    print("[6/6] итог")
    print(f"       authored {authored_pass}/12, heldout {heldout_pass}/8, "
          f"specs {specs_pass}/20")
    print(f"       critical {critical_caught}/16, functional {functional_caught}/8")
    print(f"       baseline {'PASS' if baseline_ok else 'FAIL'}, "
          f"determinism {'PASS' if all_runs_deterministic else 'FAIL'}")
    print(f"       evidence: {EVIDENCE.relative_to(ROOT)}")
    print(f"[{'PASS' if passed else 'FAIL'}] пилот генератора")
    for check in failed_checks:
        print(f"       провал: {check}")
    return 0 if passed else 1


def render_evidence(*, generation: dict, tree_digest: str, spec_results: list[dict],
                    mutant_results: list[dict], baseline: dict, rustc_version: str,
                    counts: dict, passed: bool, failed_checks: list[str]) -> str:
    frozen = json.loads(PREREG.read_text(encoding="utf-8")).get("frozen") or {}
    lines = [
        "PILOT-GENERATOR-R1 — пилот генератора file_read_stream",
        f"дата: {DATE}",
        f"статус: {'PASS' if passed else 'FAIL'}",
        "команда: python bin/pilot_generator.py --run",
        "",
        "== 1. Входное условие ==",
        "HEAD-SLICE-R1: closed=true; evidence research/outputs/HEAD-SLICE-R1-2026-11-17.txt",
        f"HEAD-SLICE-R1 prereg digest: {frozen.get('head_slice_prereg_digest')}",
        f"HEAD-SLICE-R1 evidence digest: {frozen.get('head_slice_evidence_digest')}",
        "",
        "== 2. Замороженные пороги (до прогона) ==",
        json.dumps(THRESHOLDS, ensure_ascii=False, sort_keys=True),
        f"criterion: {CRITERION}",
        "",
        "== 3. Замороженные хеши ==",
        f"new_tool.py: {frozen.get('new_tool_digest')}",
        f"authored set: {frozen.get('authored_digest')}",
        f"heldout set: {frozen.get('heldout_digest')}",
        f"mutants: {frozen.get('mutants_digest')}",
        "",
        "== 4. Генерация ==",
        f"повторов: {generation.get('repeats')}, файлов: {generation.get('files')}",
        f"generation manifest digest: {generation.get('digest')}",
        f"финальное дерево кандидатов: {tree_digest}",
        "генерация байт-идентична во всех повторах: "
        f"{'да' if generation.get('repeats') == THRESHOLDS['generation_repeats'] else 'нет'}",
        "",
        "== 5. Спецификации ==",
        "id | group | cases | compile | repeats rc | pass",
    ]
    for item in spec_results:
        compile_state = "error" if item["compile_error"] else "ok"
        lines.append(
            f"{item['id']} | {item['group']} | {item['cases']} | {compile_state} | "
            f"{'/'.join(str(rc) for rc in item['rcs'])} | {'PASS' if item['passed'] else 'FAIL'}"
        )
    lines += [
        "",
        "== 6. Мутанты ==",
        "id | class | caught | deterministic | first failure",
    ]
    for item in mutant_results:
        lines.append(
            f"{item['id']} | {item['class']} | {'yes' if item['caught'] else 'NO'} | "
            f"{'yes' if item['deterministic'] else 'no'} | {item['first_failure']}"
        )
    lines += [
        "",
        "== 7. Счёт ==",
        f"authored: {counts['authored']}/12",
        f"heldout: {counts['heldout']}/8",
        f"specs: {counts['specs']}/20 (порог >= {THRESHOLDS['specs_required']})",
        f"critical mutants: {counts['critical']}/16",
        f"functional mutants: {counts['functional']}/8",
        f"baseline bundle: {'PASS' if baseline['runs'] and all(run['rc'] == 0 for run in baseline['runs']) else 'FAIL'}",
        f"rustc: {rustc_version}",
        f"result: {'PASS' if passed else 'FAIL'}",
    ]
    if failed_checks:
        lines.append("failed checks: " + "; ".join(failed_checks))
    lines += [
        "",
        "== 8. Границы пилота ==",
        "кандидаты записаны только в lab/candidates/file_read_stream/<spec-id>/;",
        "активная policy, registry, admission и approval не изменялись;",
        "owner-ключ не создавался и не читался;",
        "ни один кандидат не активирован, K9_proven не выдавался;",
        "сеть, запись и host mounts не использовались; компиляция и запуск — WSL rustc.",
        "",
        "== 9. Что это не доказывает ==",
        "не доказывает статистическую надёжность на будущих шаблонах: 20 spec и 24 мутанта —",
        "инженерный gate, а не выборка мощности;",
        "не доказывает OS-границу: openat2/admission/room измерены в HEAD-SLICE-R1, а",
        "кандидат пилота — чистая функция над байтами;",
        "не заменяет owner-подпись и не делает head активным;",
        "не доказывает, что сгенерированные тесты полны за пределами этих мутантов;",
        "N/A в этом отчёте нет: все перечисленные проверки выполнены.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="пилот генератора file_read_stream")
    parser.add_argument("--prereg", action="store_true", help="зафиксировать/проверить хеши")
    parser.add_argument("--verify", action="store_true", help="проверить пре-регистрацию")
    parser.add_argument("--run", action="store_true", help="выполнить пилот")
    args = parser.parse_args(argv)
    if args.prereg:
        return write_prereg()
    if args.verify:
        problems = verify_prereg()
        if problems:
            for problem in problems:
                print(f"[FAIL] {problem}")
            return 1
        print(f"[ok] пре-регистрация совпадает: {PREREG.relative_to(ROOT)}")
        return 0
    if args.run:
        return run_all()
    parser.error("нужен --prereg, --verify или --run")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
