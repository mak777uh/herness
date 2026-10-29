#!/usr/bin/env python3
"""hs — прибор харнесса: факты среды, прогоны, гейты.

Правило: любое число, которое печатает этот инструмент, воспроизводимо командой,
показанной рядом с ним. Если команды нет — это не результат.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
RUNS = ROOT / "runs"
IS_WIN = sys.platform == "win32"


# ---------------------------------------------------------------- helpers

def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def run_capture(cmd: list[str], timeout: int = 20, env: dict | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env, text=True, errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as exc:
        return 126, str(exc)


def first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def cli_path() -> Path | None:
    env = os.environ.get("DSH_CLI")
    if env:
        p = Path(env)
        return p if p.exists() else None
    local = os.environ.get("LOCALAPPDATA")
    if local:
        p = Path(local) / "Programs/DeepSeek Harness/resources/runtime/cli/bin/dsh.cmd"
        if p.exists():
            return p
    found = shutil.which("dsh")
    return Path(found) if found else None


def cli_command(cli: Path, args: list[str]) -> list[str]:
    """Prefer invoking the Electron binary directly: one process, no cmd wrapper,
    so a timeout can kill the whole tree instead of orphaning grandchildren."""
    if cli.suffix.lower() in {".cmd", ".bat"} and len(cli.parents) >= 5:
        exe = cli.parents[4] / "DeepSeek Harness.exe"
        js = cli.parents[4] / "resources/app.asar/dsh/node_modules/@deepseek-ai/dsh-desktop-host/lib/cli.js"
        if exe.exists() and js.exists():
            return [str(exe), "--expose-internals", str(js), *args]
        return ["cmd", "/c", str(cli), *args]
    return [str(cli), *args]


def mem_gb() -> tuple[float, float]:
    if IS_WIN:
        class MSX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        st = MSX()
        st.dwLength = ctypes.sizeof(MSX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullTotalPhys / 2**30, st.ullAvailPhys / 2**30
    info = {}
    with open("/proc/meminfo") as fh:
        for line in fh:
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0]) * 1024
    return info["MemTotal"] / 2**30, info["MemAvailable"] / 2**30


def disk_gb(path: Path) -> tuple[float, float]:
    usage = shutil.disk_usage(str(path))
    return usage.free / 2**30, usage.total / 2**30


def collect_tools() -> dict[str, str]:
    out: dict[str, str] = {}
    for name, cmd in {
        "node": ["node", "--version"],
        "python": ["python", "--version"],
        "git": ["git", "--version"],
        "pwsh": ["pwsh", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
        "cargo": ["cargo", "--version"],
        "go": ["go", "version"],
        "forge": ["forge", "--version"],
        "lake": ["lake", "--version"],
    }.items():
        rc, text = run_capture(cmd, timeout=25)
        out[name] = first_line(text) if rc == 0 else f"(нет: rc={rc})"
    return out


# ---------------------------------------------------------------- facts

def cmd_facts(args) -> int:
    total_mem, free_mem = mem_gb()
    free_disk, total_disk = disk_gb(ROOT)
    cli = cli_path()
    dsh_version = "(нет CLI)"
    if cli:
        rc, text = run_capture(cli_command(cli, ["--version"]), timeout=60)
        dsh_version = first_line(text) if rc == 0 else f"(ошибка rc={rc})"

    facts = {
        "at": now_iso(),
        "os": {
            "platform": platform.platform(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "cpu_logical": os.cpu_count(),
        "mem_gb": {"total": round(total_mem, 1), "free": round(free_mem, 1)},
        "disk_gb": {"free": round(free_disk, 1), "total": round(total_disk, 1)},
        "dsh": {"cli": str(cli) if cli else None, "version": dsh_version},
        "tools": collect_tools(),
        "repo": str(ROOT),
    }

    if args.md:
        rows = [
            ("поле", "значение"),
            ("---", "---"),
            ("ОС", facts["os"]["platform"]),
            ("CPU (логических)", facts["cpu_logical"]),
            ("RAM, ГБ (всего/свободно)", f'{facts["mem_gb"]["total"]} / {facts["mem_gb"]["free"]}'),
            ("Диск, ГБ (свободно/всего)", f'{facts["disk_gb"]["free"]} / {facts["disk_gb"]["total"]}'),
            ("DSH CLI", facts["dsh"]["cli"] or "(нет)"),
            ("DSH версия", facts["dsh"]["version"]),
        ]
        rows.extend((f"`{k}`", f"`{v}`") for k, v in facts["tools"].items())
        for a, b in rows:
            print(f"| {a} | {b} |")
    else:
        print(json.dumps(facts, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- doctor

def cmd_doctor(args) -> int:
    checks: list[tuple[bool, str]] = []

    cli = cli_path()
    checks.append((cli is not None, f"CLI найден: {cli}" if cli else "CLI не найден (DSH_CLI / LOCALAPPDATA)"))

    if cli:
        rc, text = run_capture(cli_command(cli, ["--version"]), timeout=60)
        checks.append((rc == 0, f"dsh --version -> {first_line(text) or rc}"))

    home = Path(args.home).resolve() if args.home else HOME
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DSH_HOME"] = str(home)
    env.pop("DSH_PROFILE", None)
    if cli:
        rc, text = run_capture(cli_command(cli, ["--profile", "headless", "--dump-config"]), timeout=120, env=env)
        ok = rc == 0 and "dsh-base" in text
        checks.append((ok, f"профиль headless собирается в {home.name} (rc={rc})"))

    free_disk, _ = disk_gb(ROOT)
    checks.append((free_disk >= 5, f"диск свободно {free_disk:.1f} ГБ (порог 5)"))

    total_mem, free_mem = mem_gb()
    checks.append((free_mem >= 2.5, f"RAM свободно {free_mem:.1f} ГБ (порог 2.5)"))

    for ok, msg in checks:
        print(f"[{'ok' if ok else 'FAIL'}] {msg}")
    failed = [m for ok, m in checks if not ok]
    print(f"\nитог: {len(checks) - len(failed)}/{len(checks)} ok")
    return 0 if not failed else 1


# ---------------------------------------------------------------- run

def _kill_tree(proc: subprocess.Popen) -> None:
    if IS_WIN:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except OSError:
            proc.kill()


def cmd_run(args) -> int:
    cli = cli_path()
    if not cli:
        print("CLI не найден: задайте DSH_CLI", file=sys.stderr)
        return 2

    home = Path(args.home).resolve() if args.home else HOME
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DSH_HOME"] = str(home)
    env.pop("DSH_PROFILE", None)

    cmd = cli_command(cli, ["--profile", args.profile, args.task])
    kwargs = {}
    if IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    started = now_iso()
    t0 = time.perf_counter()
    timed_out = False
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **kwargs) as proc:
        try:
            out, err = proc.communicate(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
            out, err = proc.communicate()
    duration = time.perf_counter() - t0

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + digest(args.task.encode())[:6]
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "stdout.txt").write_bytes(out)
    (run_dir / "stderr.log").write_bytes(err)

    meta = {
        "run_id": run_id,
        "started": started,
        "duration_s": round(duration, 2),
        "exit_code": None if timed_out else proc.returncode,
        "timed_out": timed_out,
        "profile": args.profile,
        "task": args.task,
        "home": str(home),
        "cmd": cmd[:2] + ["…"] if len(cmd) > 2 else cmd,
        "stdout_sha256": digest(out),
        "stderr_sha256": digest(err),
        "stdout_bytes": len(out),
        "stderr_bytes": len(err),
        "facts": {"os": platform.platform(), "cpu": os.cpu_count()},
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    RUNS.mkdir(parents=True, exist_ok=True)
    with (RUNS / "index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"run_id": run_id, "exit": meta["exit_code"], "s": meta["duration_s"],
                             "stdout": meta["stdout_sha256"]}, ensure_ascii=False) + "\n")

    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print("\nчто это не доказывает: успешный код возврата не подтверждает, что модель не выдумала")
    print("факт; истинность содержимого проверяет слой истины, а не код выхода.")
    return 0 if meta["exit_code"] == 0 else 1


# ---------------------------------------------------------------- bench

def cmd_bench(args) -> int:
    """Cold start with --dump-config: no model call, no cost, measurable."""
    cli = cli_path()
    if not cli:
        print("CLI не найден", file=sys.stderr)
        return 2
    home = Path(args.home).resolve() if args.home else HOME
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DSH_HOME"] = str(home)
    env.pop("DSH_PROFILE", None)

    samples = []
    for _ in range(args.n):
        t0 = time.perf_counter()
        rc, _text = run_capture(cli_command(cli, ["--profile", "headless", "--dump-config"]), timeout=180, env=env)
        samples.append(time.perf_counter() - t0)
        if rc != 0:
            print(f"прогон упал rc={rc}", file=sys.stderr)
            return 1
    samples.sort()
    p50 = samples[len(samples) // 2]
    print(json.dumps({"n": len(samples), "seconds": [round(s, 2) for s in samples],
                      "p50": round(p50, 2), "min": round(samples[0], 2),
                      "max": round(samples[-1], 2), "mode": "dump-config (без модели)"},
                     ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- gates

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{20,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"\b0x[0-9a-fA-F]{64}\b"),
]

SKIP_DIRS = {".git", "node_modules", "home", "runs", "refs-cache", "__pycache__", ".venv", "dist", "build"}
TEXT_EXT = {".md", ".py", ".ts", ".js", ".json", ".yml", ".yaml", ".toml", ".txt", ".ps1", ".sh", ".cfg", ".ini"}


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in TEXT_EXT and p.stat().st_size < 1_000_000:
                yield p


def gate_secrets(root: Path) -> list[str]:
    problems = []
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat in SECRET_PATTERNS:
                if pat.search(line):
                    problems.append(f"{path.relative_to(root)}:{lineno}: подозрение на секрет ({pat.pattern[:28]}…)")
                    break
    return problems


def gate_claims(root: Path) -> list[str]:
    claims = root / "CLAIMS.md"
    if not claims.exists():
        return ["CLAIMS.md отсутствует"]
    problems = []
    for lineno, line in enumerate(claims.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("| C-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            problems.append(f"CLAIMS.md:{lineno}: строка без 6 полей")
            continue
        cid, text, ctype, cmd, artifact, _date = cells[:6]
        if not cmd or not artifact:
            problems.append(f"CLAIMS.md:{lineno}: {cid} без команды или артефакта")
        if ctype not in {"proof", "test", "statistics", "observation", "judgment"}:
            problems.append(f"CLAIMS.md:{lineno}: {cid} неизвестный тип '{ctype}'")
        if ctype != "proof" and re.search(r"(?i)доказан|гарантир|всегда", text):
            problems.append(f"CLAIMS.md:{lineno}: {cid} формулировка сильнее типа ({ctype})")
    return problems


LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def gate_links(root: Path) -> list[str]:
    problems = []
    for path in iter_files(root):
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for target in LINK_RE.findall(text):
            target = target.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                problems.append(f"{path.relative_to(root)}: битая ссылка -> {target}")
    return problems


def gate_criteria(root: Path) -> list[str]:
    sys.path.insert(0, str(ROOT))
    from core import criteria
    return criteria.problems(root)


def cmd_refs(args) -> int:
    sys.path.insert(0, str(ROOT))
    from core import refs

    if args.action == "sync":
        stats = refs.sync(args.repo)
        print(json.dumps(stats, ensure_ascii=False))
        return 0 if stats["fetched"] else 1
    if args.action == "add":
        if not args.query:
            print("нужен адрес: refs add <url>", file=sys.stderr)
            return 2
        print(json.dumps(refs.add(args.query), ensure_ascii=False))
        return 0
    if args.action == "search":
        if not args.query:
            print("нужен запрос: refs search \"<что ищем>\"", file=sys.stderr)
            return 2
        print(refs.render_search(args.query, args.k))
        return 0
    if args.action == "list":
        for row in refs.summary():
            print(f"{row['id']:<28} документов {row['docs']:<2} {row['bytes']:>7} b  {', '.join(row['docs_list'])}")
        return 0
    return 2


def _dir_gb(path: Path) -> float:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total / 2**30


def cmd_tools(args) -> int:
    """Инвентарь тулчейнов: что уже стоит, сколько занимает, что сломано."""
    home = Path.home()
    elan = home / ".elan" / "toolchains"
    rows = []

    if elan.exists():
        for tc in sorted(elan.iterdir()):
            if not tc.is_dir():
                continue
            lake = tc / "bin" / "lake.exe" if IS_WIN else tc / "bin" / "lake"
            rows.append({"toolchain": tc.name, "gb": round(_dir_gb(tc), 2),
                         "lake": lake.exists()})

    for name, path in (("rustup", home / ".rustup"), ("cargo", home / ".cargo"),
                       ("foundry", home / ".foundry"), ("lake-cache", home / ".lake")):
        if path.exists():
            rows.append({"toolchain": name, "gb": round(_dir_gb(path), 2), "lake": None})

    versions = {}
    for name, exe in (("cargo", home / ".cargo" / "bin" / ("cargo.exe" if IS_WIN else "cargo")),
                      ("forge", home / ".foundry" / "bin" / ("forge.exe" if IS_WIN else "forge")),
                      ("lean", home / ".elan" / "bin" / ("lean.exe" if IS_WIN else "lean"))):
        if exe.exists():
            rc, text = run_capture([str(exe), "--version"], timeout=30)
            versions[name] = first_line(text) if rc == 0 else f"(ошибка rc={rc})"

    total = round(sum(r["gb"] for r in rows), 2)
    payload = {"toolchain_dirs": rows, "versions": versions, "total_gb": total}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    broken = [r["toolchain"] for r in rows if r["lake"] is False]
    if broken:
        print(f"\n[!] без lake: {', '.join(broken)} — эти тулчейны не собирают Lean-проекты")
    return 0


def cmd_criteria(args) -> int:
    sys.path.insert(0, str(ROOT))
    from core import criteria

    data = criteria.summary(ROOT)
    print(f"критериев: {data['total']}")
    for status, count in sorted(data["counts"].items(), key=lambda kv: -kv[1]):
        print(f"  {status:<14} {count}")
    if data["open_judgments"]:
        print(f"  без замера (суждение): {', '.join(data['open_judgments'])}")
    if data["refuted"]:
        print(f"  опровергнуто: {', '.join(data['refuted'])}")
    issues = criteria.problems(ROOT)
    for issue in issues:
        print(f"  [!] {issue}")
    return 0 if not issues else 1



def gate_audit(root: Path) -> list[str]:
    sys.path.insert(0, str(ROOT))
    from core import audit
    return audit.problems(root)


def cmd_audit(args) -> int:
    sys.path.insert(0, str(ROOT))
    from core import audit

    data = audit.summary(ROOT)
    print(f"заметок: {data['total']}  находок: {len(data['findings'])}  мнений: {len(data['opinions'])}  некорректных: {len(data['invalid'])}  виды: {data['kinds']}")
    if data["findings"]:
        print("\nнаходки:")
        for n in data["findings"]:
            print(f"  [{n.get('severity', '?'):<6}] -> {n['_target']:<12} {n.get('about', ''):<18} {(n.get('finding') or '')[:90]}")
    if data["opinions"]:
        print("\nмнения без воспроизводящего случая (в совет не идут):")
        for n in data["opinions"]:
            print(f"  -> {n['_target']:<12} {(n.get('finding') or '')[:90]}")
    if data["repeats"]:
        print("\nповторяющиеся:")
        for (target, finding), count in data["repeats"][:5]:
            if count > 1:
                print(f"  ×{count} -> {target}: {finding[:80]}")
    issues = audit.problems(ROOT)
    for issue in issues:
        print(f"  [!] {issue}")
    return 0 if not issues else 1


def cmd_request(args) -> int:
    sys.path.insert(0, str(ROOT))
    from core.contracts import ContractError, Request

    if getattr(args, "corpus", False):
        cases = sorted((ROOT / "lab" / "requests" / "corpus").glob("*.json"))
        bad = 0
        for case_path in cases:
            data = json.loads(case_path.read_text(encoding="utf-8"))
            kwargs = {k: (tuple(v) if isinstance(v, list) else v) for k, v in data.get("parsed", {}).items()}
            try:
                Request(**kwargs).validate()
                print(f"[ok] {case_path.name}")
            except (ContractError, TypeError) as exc:
                bad += 1
                print(f"[FAIL] {case_path.name}: {exc}")
        print(f"\nкорпус: {len(cases) - bad}/{len(cases)} ok")
        return 0 if not bad else 1

    if not args.file:
        print("нужен файл разбора или --corpus", file=sys.stderr)
        return 2
    path = Path(args.file)
    if not path.exists():
        print(f"нет файла: {path}", file=sys.stderr)
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))
    kwargs = {k: (tuple(v) if isinstance(v, list) else v) for k, v in data.items()}
    try:
        req = Request(**kwargs)
        req.validate()
    except (ContractError, TypeError) as exc:
        print(f"[FAIL] {exc}")
        return 1
    print(f"цель: {req.goal}")
    print(f"определено: {len(req.defined)}  не определено: {len(req.undefined)}")
    print(f"вопросов: {len(req.questions)}  экспериментов: {len(req.experiments)}  допущений: {len(req.assumptions)}")
    print(f"действия: {', '.join(req.next_actions)}")
    if req.contradictions:
        print(f"[!] противоречия: {'; '.join(req.contradictions)}")
    return 0


def cmd_ping(args) -> int:
    sys.path.insert(0, str(ROOT))
    from core.http_provider import OpenAICompatProvider

    provider = OpenAICompatProvider(args.base, args.model, args.key_env)
    if not provider.has_key():
        print(f"нет ключа в переменной {args.key_env}", file=sys.stderr)
        return 2
    try:
        result = provider.complete([{"role": "user", "content": "ответь одним словом: ok"}],
                                   stream=not args.no_stream)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}")
        return 1
    print(json.dumps({
        "status": result.status,
        "latency_ms": result.latency_ms,
        "chunks": result.raw_chunks,
        "text": result.reply.text[:80],
        "usage": result.reply.usage,
        "model": args.model,
    }, ensure_ascii=False, indent=2))
    return 0


def gate_failures(root: Path) -> list[str]:
    sys.path.insert(0, str(ROOT))
    from core import failures
    return failures.problems(root)


def cmd_failures(args) -> int:
    sys.path.insert(0, str(ROOT))
    from core import failures

    data = failures.summary(ROOT)
    print(f"отказов: {data['total']}")
    for cls, count in sorted(data["classes"].items(), key=lambda kv: -kv[1]):
        print(f"  {cls:<20} {count}")
    for case in data["cases"]:
        print(f"  {case.get('id')} [{case.get('class')}] {case.get('what','')[:90]}")
    issues = failures.problems(ROOT)
    for issue in issues:
        print(f"  [!] {issue}")
    return 0 if not issues else 1

def cmd_gates(args) -> int:
    root = Path(args.root).resolve()
    checks = [("секреты", gate_secrets), ("утверждения", gate_claims),
              ("ссылки", gate_links), ("критерии", gate_criteria), ("аудит", gate_audit), ("отказы", gate_failures)]
    total = 0
    for name, fn in checks:
        problems = fn(root)
        total += len(problems)
        print(f"[{'ok' if not problems else 'FAIL'}] {name}: {len(problems)} проблем")
        for p in problems[:20]:
            print(f"   - {p}")
    return 0 if total == 0 else 1


# ---------------------------------------------------------------- selftest

def cmd_selftest(args) -> int:
    """Negative tests: a gate that cannot fail proves nothing."""
    results: list[tuple[bool, str]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        secret_file = tmpdir / "leak.md"
        secret_file.write_text('api_key = "sk-' + "a" * 24 + '"\n', encoding="utf-8")
        hits = gate_secrets(tmpdir)
        results.append((len(hits) == 1, f"детектор секретов ловит посаженный ключ (найдено {len(hits)})"))

        bad_claims = tmpdir / "CLAIMS.md"
        bad_claims.write_text("| C-9999 | это доказано | observation | | | |\n", encoding="utf-8")
        hits = gate_claims(tmpdir)
        results.append((len(hits) >= 1, f"линтер утверждений отбивает «доказано» без proof (найдено {len(hits)})"))

        (tmpdir / "a.md").write_text("[битая](nope.md)\n", encoding="utf-8")
        hits = [p for p in gate_links(tmpdir) if "nope.md" in p]
        results.append((len(hits) == 1, "проверка ссылок ловит битую"))

    old = os.environ.get("DSH_CLI")
    os.environ["DSH_CLI"] = str(ROOT / "definitely-not-here.cmd")
    try:
        results.append((cli_path() is None, "CLI-резолвер отбивает несуществующий путь"))
    finally:
        if old is None:
            os.environ.pop("DSH_CLI", None)
        else:
            os.environ["DSH_CLI"] = old

    for suite in ("test_contracts.py", "test_m1_journal.py", "test_provider.py", "test_http_provider.py", "test_audit.py", "test_failures.py"):
        path = ROOT / "tests" / suite
        if path.exists():
            proc = subprocess.run([sys.executable, str(path)], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            tail = (proc.stdout.strip().splitlines() or ["нет вывода"])[-1]
            results.append((proc.returncode == 0, f"{suite}: {tail}"))

    with tempfile.TemporaryDirectory() as tmp3:
        docs = Path(tmp3) / "docs"
        docs.mkdir(parents=True)
        (docs / "CRITERIA.md").write_text("| K9 | нечто | неизвестно | | |\n", encoding="utf-8")
        issues = gate_criteria(Path(tmp3))
        results.append((len(issues) >= 1, f"реестр критериев отбивает строку без способа установления ({len(issues)} замечаний)"))

    for ok, msg in results:
        print(f"[{'ok' if ok else 'FAIL'}] {msg}")
    return 0 if all(ok for ok, _ in results) else 1


# ---------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="hs", description="прибор харнесса")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("facts", help="факты среды")
    p.add_argument("--md", action="store_true", help="вывод таблицей markdown")
    p.set_defaults(func=cmd_facts)

    p = sub.add_parser("doctor", help="проверка среды")
    p.add_argument("--home", help="свой DSH_HOME")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("run", help="один прогон задачи через dsh headless")
    p.add_argument("task")
    p.add_argument("--profile", default="headless")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--home")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("bench", help="холодный старт без вызова модели")
    p.add_argument("-n", type=int, default=3)
    p.add_argument("--home")
    p.set_defaults(func=cmd_bench)

    sub.add_parser("audit", help="заметки аудита: находки и мнения").set_defaults(func=cmd_audit)
    sub.add_parser("failures", help="корпус отказов процесса").set_defaults(func=cmd_failures)

    p = sub.add_parser("request", help="проверить разбор запроса")
    p = sub.add_parser("ping", help="живая проверка провайдера")
    p.add_argument("--base", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--key-env", default="OPENCODE_API_KEY")
    p.add_argument("--no-stream", action="store_true")
    p.set_defaults(func=cmd_ping)

    p.add_argument("file", nargs="?")
    p.add_argument("--corpus", action="store_true", help="проверить корпус регрессии")
    p.set_defaults(func=cmd_request)

    p = sub.add_parser("gates", help="секреты, утверждения, ссылки")
    p.add_argument("--root", default=str(ROOT))
    p.set_defaults(func=cmd_gates)

    p = sub.add_parser("refs", help="справочник: репозитории и внешние источники")
    p.add_argument("action", choices=["sync", "search", "list", "add"])
    p.add_argument("query", nargs="?")
    p.add_argument("-k", type=int, default=8)
    p.add_argument("--repo", nargs="*", help="только эти источники")
    p.set_defaults(func=cmd_refs)

    sub.add_parser("criteria", help="реестр критериев и их статусов").set_defaults(func=cmd_criteria)
    sub.add_parser("tools", help="инвентарь тулчейнов: размеры, версии, поломки").set_defaults(func=cmd_tools)

    sub.add_parser("selftest", help="негативные тесты инструмента").set_defaults(func=cmd_selftest)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))








