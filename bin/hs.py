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
    so a timeout can kill the whole tree instead of orphaning grandchildren.

    Путь к cli.js лежит внутри app.asar и виртуален: файловая система его не видит,
    читает его Electron. Поэтому существование не проверяем.
    """
    if cli.suffix.lower() in {".cmd", ".bat"} and len(cli.parents) >= 5:
        exe = cli.parents[4] / "DeepSeek Harness.exe"
        js = cli.parents[3] / "app.asar/dsh/node_modules/@deepseek-ai/dsh-desktop-host/lib/cli.js"
        if exe.exists():
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
    env["ELECTRON_RUN_AS_NODE"] = "1"
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
    env["ELECTRON_RUN_AS_NODE"] = "1"
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
    env["ELECTRON_RUN_AS_NODE"] = "1"
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

SKIP_DIRS = {".git", "node_modules", "home", "runs", "refs-cache", "__pycache__", ".venv", "dist", "build", "sessions", "out", ".secrets"}
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
        if ctype not in {"proof", "test", "statistics", "observation", "judgment", "withdrawn", "not established"}:
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
    if args.action == "watch":
        before = refs.snapshot()
        stats = refs.sync(args.repo)
        changes = refs.diff(before, refs.snapshot())
        print(json.dumps({"fetched": stats["fetched"], "changes": len(changes)}, ensure_ascii=False))
        for c in changes:
            print(f"  {c['status']:<10} {c['source']}/{c['doc']}  {c['from']} -> {c['to']}")
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

    extra = {}
    if getattr(args, "session", None):
        # Go-эндпоинт требует стабильный id разговора: без него 400 MissingSessionID
        extra["x-opencode-session"] = args.session
    provider = OpenAICompatProvider(args.base, args.model, args.key_env, extra_headers=extra)
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


def cmd_execute(args) -> int:
    """Прогон собственным циклом (mock) с отчётом: задача → журнал → артефакты → report.md."""
    sys.path.insert(0, str(ROOT))
    from core import report
    from core.journal import Journal
    from core.loop import MockProvider, Step, run as loop_run
    from core.tools import ShellTool

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-mock"
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    provider = MockProvider([
        Step(tool={"name": "shell", "args": {"command": f"echo {args.task}"}}),
        Step(text="прогон завершён (mock): инструмент вызван, артефакт записан"),
    ])
    journal = Journal(run_dir)
    result = loop_run(args.task, provider, ShellTool(ROOT), journal, max_steps=args.steps)

    boundaries = (
        "mock-прогон: модель не вызывалась, ответ сценария заранее задан",
        "поведение на реальном ответе модели не проверено",
        "артефакт содержит вывод оболочки, а не проверенный факт о мире",
    )
    path = report.write(run_dir, args.task, boundaries=boundaries)
    print(json.dumps({"run": run_id, "status": result["status"], "steps": result["steps"],
                      "report": str(path)}, ensure_ascii=False, indent=2))
    return 0


def cmd_live(args) -> int:
    """Живой прогон нашим циклом: модель → инструмент → журнал → артефакт → отчёт."""
    sys.path.insert(0, str(ROOT))
    from core import report
    from core.http_provider import OpenAICompatProvider
    from core.journal import Journal
    from core.live import LiveProvider
    from core.loop import run as loop_run
    from core.tools import ShellTool

    extra = {}
    if args.session:
        extra["x-opencode-session"] = args.session
    client = OpenAICompatProvider(args.base, args.model, args.key_env, extra_headers=extra)
    if not client.has_key():
        print(f"нет ключа: {args.key_env}", file=sys.stderr)
        return 2

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-live"
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    provider = LiveProvider(client, args.task, max_steps=args.steps)
    journal = Journal(run_dir)
    started = time.perf_counter()
    try:
        result = loop_run(args.task, provider, ShellTool(Path(args.cwd or ROOT)), journal,
                          max_steps=args.steps)
    finally:
        elapsed = round(time.perf_counter() - started, 1)

    boundaries = (
        f"живой прогон: модель {args.model}, шагов {result['steps']}, время {elapsed}s",
        "ответ модели не проверялся третьей стороной: это её вывод, а не факт о мире",
        "вывод инструментов записан как артефакт, но его истинность не проверялась",
    )
    path = report.write(run_dir, args.task, boundaries=boundaries)
    print(json.dumps({"run": run_id, "status": result["status"], "steps": result["steps"],
                      "seconds": elapsed, "report": str(path)}, ensure_ascii=False, indent=2))
    return 0


def cmd_record(args) -> int:
    """Записать событие в журнал прогона (для работы агента руками)."""
    sys.path.insert(0, str(ROOT))
    from core.journal import Journal

    run_dir = RUNS / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    journal = Journal(run_dir)
    try:
        if args.artifact:
            data = Path(args.artifact).read_bytes()
            ref = journal.put_artifact(data, Path(args.artifact).suffix or ".txt")
            journal.tool_result(args.call_id, ref, ok=True, preview=args.preview or "")
            print(json.dumps({"artifact": ref.path, "sha256": ref.sha256, "bytes": ref.bytes}, ensure_ascii=False))
        else:
            journal.event(args.type, json.loads(args.payload) if args.payload else {})
            print("ok")
    finally:
        journal.close()
    return 0


def cmd_report(args) -> int:
    """Собрать report.md из журнала готового прогона."""
    sys.path.insert(0, str(ROOT))
    from core import report
    from core.contracts import Claim

    claims = []
    for raw in args.claim or []:
        cid, text, ctype, origin = (raw.split("|", 3) + ["", "", "", ""])[:4]
        claims.append(Claim(id=cid.strip(), text=text.strip(), type=ctype.strip() or "observation",
                            origin=origin.strip() or "observed", evidence=("journal",),
                            not_claimed=("что это проверено повторно",)))
    try:
        path = report.write(RUNS / args.run, args.task, claims=claims, boundaries=tuple(args.boundary or ()))
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}")
        return 1
    print(str(path))
    return 0


_CD = re.compile(r'^\s*cd\s+(?:"([^"]+)"|(\S+))\s*(?:;|&&)\s*(.*)$', re.DOTALL)


def _strip_cd(command: str, base: Path) -> tuple[str, Path, bool]:
    """Убирает ведущий `cd ...;` и переносит его в рабочий каталог.

    Наблюдение из журналов: 19 372 команды начинались с cd — это служебный шум,
    а не работа. Каталог задаётся один раз.
    """
    m = _CD.match(command)
    if not m:
        return command, base, False
    target = m.group(1) or m.group(2)
    rest = m.group(3).strip()
    if not rest:
        return command, base, False
    return rest, (base / target).resolve(), True


def _find_previous_command(run_dir: Path, command: str) -> dict | None:
    """Ищет в журнале уже выполненную такую же команду: повтор нужно показать, но не отменять."""
    path = run_dir / "events.jsonl"
    if not path.exists():
        return None
    found = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "tool/call":
            continue
        if (event.get("payload", {}).get("arguments") or {}).get("command") == command:
            found = {"seq": event.get("seq"), "ts": event.get("ts")}
    return found


def _python_exe() -> Path:
    """Интерпретатор проекта: venv, если он есть, иначе текущий."""
    venv = Path(r"C:\111\env\python\.venv\Scripts\python.exe")
    return venv if venv.exists() else Path(sys.executable)


def cmd_py(args) -> int:
    """Процедура: запуск Python с правильным интерпретатором и UTF-8.

    Кристаллизация из ADR-0023: преамбула `$py=...; $env:PYTHONIOENCODING=...` повторялась
    тысячи раз. Теперь это одна команда.
    """
    exe = _python_exe()
    if args.code:
        cmd = [str(exe), "-c", args.code]
    elif args.target:
        cmd = [str(exe), args.target] + (args.args or [])
    else:
        print("нужен файл или --code", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(cmd, cwd=str(Path(args.cwd or ROOT)), env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out.rstrip())
    return proc.returncode


def cmd_budget(args) -> int:
    """Сколько потрачено в прогоне: шаги, время, объём."""
    sys.path.insert(0, str(ROOT))
    from core import budget as budget_mod

    run_dir = RUNS / args.run
    if not run_dir.exists():
        print(f"нет прогона {args.run}")
        return 2
    print(json.dumps(budget_mod.usage(run_dir), ensure_ascii=False, indent=2))
    return 0


def cmd_step(args) -> int:
    """Один шаг работы: выполнить команду и записать её в журнал как свидетельство.

    Заменяет собой пять команд ручного протоколирования: вызов, исполнение,
    артефакт, проверка дайджеста, запись результата — всё за один вызов.
    """
    sys.path.insert(0, str(ROOT))
    from core.journal import Journal
    from core.tools import ShellTool

    run_dir = RUNS / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    from core import budget as budget_mod

    over, reason = budget_mod.exceeded(run_dir, args.max_steps, args.max_seconds, args.max_bytes)
    if over:
        print(json.dumps({"stopped": reason, "usage": budget_mod.usage(run_dir)},
                         ensure_ascii=False, indent=2))
        return 3
    journal = Journal(run_dir)
    try:
        started = (run_dir / "events.jsonl").exists() and (run_dir / "events.jsonl").stat().st_size > 0
        if not started or args.start:
            journal.run_start(args.task or args.run, model="agent")
        command = args.command or ""
        if not command:
            print("нужна команда", file=sys.stderr)
            return 2
        workdir = Path(args.cwd or ROOT)
        command, workdir, normalized = _strip_cd(command, workdir)
        previous = _find_previous_command(run_dir, command)
        out = ShellTool(workdir).run(command)
        call_id = f"step-{int(time.time() * 1000)}"
        journal.tool_call(call_id, "shell", {"command": command,
                                             "repeat_of": previous["seq"] if previous else None})
        ref = journal.put_artifact(out.text.encode("utf-8"))
        journal.tool_result(call_id, ref, ok=out.ok, preview=out.text[:600])
        print(json.dumps({
            "exit": out.exit_code,
            "digest": ref.sha256[:16],
            "bytes": ref.bytes,
            "artifact": ref.path,
            "repeat_of": previous["seq"] if previous else None,
            "cwd_normalized": normalized,
            "preview": out.text[:300],
        }, ensure_ascii=False, indent=2))
        return 0 if out.ok else 1
    finally:
        journal.close()


def cmd_repeats(args) -> int:
    """Кандидаты в процедуры: что повторяется в журналах и сколько шагов это стоит."""
    sys.path.insert(0, str(ROOT))
    from core import repeats

    if args.sessions:
        single, pairs = repeats.scan_sessions(args.limit)
        source = f"сессии (выборка {args.limit or 'все'})"
    else:
        single, pairs = repeats.scan_runs(RUNS)
        source = "наши прогоны"
    cands = repeats.candidates(single, pairs, args.min_single, args.min_pair)
    print(f"источник: {source}; вызовов: {sum(single.values())}; кандидатов: {len(cands)}")
    for c in cands[: args.top]:
        mark = "связка" if c["kind"] == "pair" else "команда"
        print(f"  ×{c['count']:<6} {mark:<8} {c['what']}")
    return 0


def cmd_reply(args) -> int:
    """Какой тип ответа нужен задаче: исполнять, спросить, искать, отказать."""
    sys.path.insert(0, str(ROOT))
    from core import reply

    out = reply.decide(args.task)
    print(f"тип: {out['type']}")
    print(f"почему: {out['reason']}")
    if out.get("alternatives"):
        print(f"альтернативы: {', '.join(out['alternatives'])}")
    print(f"близость к классу: {out['score']:.3f}")
    return 0


def cmd_route(args) -> int:
    """Семантическая раскладка задачи по классам и инструментам."""
    sys.path.insert(0, str(ROOT))
    from core import routing

    rows = routing.route(args.task, args.top)
    if not rows:
        print("нет совпадений: задача не похожа ни на один класс (это тоже ответ)")
        return 0
    for row in rows:
        tools = ", ".join(row["tools"]) or "—"
        print(f"  {row['class']} {row['name']:<22} score {row['score']:.3f}  инструменты: {tools}")
    return 0


def cmd_learn(args) -> int:
    """Запись результата и предложение новых классов по накоплению."""
    sys.path.insert(0, str(ROOT))
    from core import routing

    if args.propose:
        proposals = routing.propose_classes(args.min_support)
        if not proposals:
            print(f"предложений нет: нужно ≥{args.min_support} успешных задач вне известных классов")
            return 0
        for prop in proposals:
            print(f"  поддержка {prop['support']}; общие термины: {', '.join(prop['shared_terms'])}; "
                  f"инструменты: {', '.join(prop['tools'])}")
        return 0

    if not args.task or not args.tool:
        print("нужны --task и --tool (или --propose)", file=sys.stderr)
        return 2
    record = routing.learn(args.task, args.tool, args.cls, not args.fail)
    print(json.dumps(record, ensure_ascii=False))
    return 0


def cmd_spread(args) -> int:
    """Куда инструменты могут пойти дальше: соседние классы, где выигрыш ещё не проверен."""
    sys.path.insert(0, str(ROOT))
    from core import propagation

    classes = propagation.load_classes()
    tools = propagation.load_tools()
    rows = []
    for tool in tools:
        rows.extend(propagation.suggest(tool, classes, args.min_advantage, args.min_similarity))
    print(f"инструментов: {len(tools)}; предложений переноса: {len(rows)}")
    for row in rows:
        print(f"  {row['tool']}: {row['from']} → {row['to']}  ({row['reason']})")
    if not rows:
        print("  переносить нечего: либо нет измеренного выигрыша, либо соседние классы уже пробованы")
    return 0


def cmd_procs(args) -> int:
    """Реестр процедур: что кристаллизовано и чем проверяется."""
    path = ROOT / "procedures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("procedures", [])
    problems = []
    seen = set()
    for row in rows:
        pid = row.get("id", "")
        if pid in seen:
            problems.append(f"дубликат id {pid}")
        seen.add(pid)
        for field in ("id", "name", "what", "selftest", "status"):
            if not row.get(field):
                problems.append(f"{pid}: нет поля {field}")
        if row.get("status") not in {"active", "candidate", "retired"}:
            problems.append(f"{pid}: неизвестный статус {row.get('status')!r}")
    print(f"процедур: {len(rows)}")
    for row in rows:
        print(f"  {row.get('id')} [{row.get('status'):<9}] {row.get('name'):<16} заменяет: {str(row.get('replaces'))[:60]}")
    for issue in problems:
        print(f"  [!] {issue}")
    return 0 if not problems else 1


def cmd_plan(args) -> int:
    sys.path.insert(0, str(ROOT))
    from core import plan as planner

    if args.compare:
        data = json.load(open(ROOT / "research" / "sessions" / "digest.json", encoding="utf-8"))
        samples = [s for s in data.get("task_samples", []) if len(s) > 40][:args.limit or 100]
        print(json.dumps(planner.compare(samples), ensure_ascii=False, indent=2))
        return 0

    if args.stats:
        data = json.load(open(ROOT / "research" / "sessions" / "digest.json", encoding="utf-8"))
        samples = [s for s in data.get("task_samples", []) if len(s) > 40][:args.limit or 100]
        print(json.dumps(planner.summarize(samples), ensure_ascii=False, indent=2))
        return 0

    if not args.request:
        print("нужен запрос или --stats", file=sys.stderr)
        return 2
    print(json.dumps(planner.plan(args.request), ensure_ascii=False, indent=2))
    return 0

def gate_procs(root: Path) -> list[str]:
    path = root / "procedures.json"
    if not path.exists():
        return ["нет procedures.json"]
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for row in data.get("procedures", []):
        for field in ("id", "name", "what", "selftest", "status"):
            if not row.get(field):
                out.append(f"procedures.json: {row.get('id', '?')} без поля {field}")
    return out


RESERVED_WORDS = ("доказан", "гарантир", "неизбежн", "полностью исключ")
RESERVED_TYPES = {"proof", "test"}


def gate_wording(root: Path) -> list[str]:
    """Потолок формулировки: слово силы допустимо только для типа, который его выдерживает.

    Правило взято из портфеля (docs/CLAIMS.md в spec и flowguard-spec): утверждение не может быть
    сформулировано сильнее, чем позволяет тип свидетельства.
    """
    claims = root / "CLAIMS.md"
    if not claims.exists():
        return []
    problems = []
    for lineno, line in enumerate(claims.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("| C-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        cid, text, ctype = cells[0], cells[1].lower(), cells[2].lower()
        for word in RESERVED_WORDS:
            if word in text and ctype not in RESERVED_TYPES:
                problems.append(f"CLAIMS.md:{lineno}: {cid} — слово «{word}» при типе {ctype!r}")
    return problems

def gate_readme_numbers(root: Path) -> list[str]:
    """Документ не сильнее дерева: число в README обязано иметь владельца в CLAIMS.md.

    Механизм из портфеля (VecDHT check-status-claims): строка, утверждающая наличие, требует
    доказательства; строка, которая сильнее дерева, — находка.
    """
    readme = root / "README.md"
    claims = root / "CLAIMS.md"
    if not readme.exists() or not claims.exists():
        return []
    body = claims.read_text(encoding="utf-8")
    problems = []
    for lineno, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), 1):
        for match in re.finditer(r"\b(\d{1,4})\b", line):
            value = match.group(1)
            number = int(value)
            if 2020 <= number <= 2030:
                continue
            if value in body or str(number) in body:
                continue
            problems.append(f"README.md:{lineno}: число {value} без владельца в CLAIMS.md")
    return problems


def cmd_gates(args) -> int:
    root = Path(args.root).resolve()
    checks = [("секреты", gate_secrets), ("утверждения", gate_claims),
              ("ссылки", gate_links), ("критерии", gate_criteria), ("аудит", gate_audit), ("отказы", gate_failures), ("процедуры", gate_procs), ("формулировки", gate_wording), ("README", gate_readme_numbers)]
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

    for suite in ("test_contracts.py", "test_m1_journal.py", "test_provider.py", "test_http_provider.py", "test_report.py", "test_audit.py", "test_failures.py", "test_hohfeld.py", "test_propagation.py", "test_reply.py", "test_budget.py", "test_live.py", "test_hohfeld.py"):
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
    p.add_argument("file", nargs="?")
    p.add_argument("--corpus", action="store_true", help="проверить корпус регрессии")
    p.set_defaults(func=cmd_request)

    p = sub.add_parser("execute", help="прогон своим циклом (mock) с отчётом")
    p.add_argument("task")
    p.add_argument("--steps", type=int, default=8)
    p.set_defaults(func=cmd_execute)

    p = sub.add_parser("repeats", help="кандидаты в процедуры по журналам")
    p.add_argument("--sessions", action="store_true", help="сканировать сессии DSH (медленно)")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--min-single", type=int, default=3)
    p.add_argument("--min-pair", type=int, default=5)
    p.set_defaults(func=cmd_repeats)

    p = sub.add_parser("reply", help="какой тип ответа нужен задаче")
    p.add_argument("task")
    p.set_defaults(func=cmd_reply)

    p = sub.add_parser("route", help="разложить задачу по классам и инструментам")
    p.add_argument("task")
    p.add_argument("--top", type=int, default=3)
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("learn", help="записать результат и предложить новые классы")
    p.add_argument("--task")
    p.add_argument("--tool")
    p.add_argument("--class", dest="cls")
    p.add_argument("--fail", action="store_true")
    p.add_argument("--propose", action="store_true")
    p.add_argument("--min-support", type=int, default=3)
    p.set_defaults(func=cmd_learn)

    p = sub.add_parser("spread", help="перенос инструментов между классами задач")
    p.add_argument("--min-advantage", type=float, default=0.2)
    p.add_argument("--min-similarity", type=float, default=0.5)
    p.set_defaults(func=cmd_spread)

    sub.add_parser("procs", help="реестр процедур").set_defaults(func=cmd_procs)

    p = sub.add_parser("py", help="запустить Python проекта (venv + UTF-8)")
    p.add_argument("target", nargs="?")
    p.add_argument("args", nargs="*")
    p.add_argument("--code", help="код вместо файла")
    p.add_argument("--cwd")
    p.set_defaults(func=cmd_py)

    p = sub.add_parser("live", help="живой прогон: модель, инструмент, журнал, отчёт")
    p.add_argument("task")
    p.add_argument("--base", default="https://opencode.ai/inference/go/openai/v1")
    p.add_argument("--model", default="deepseek-v4.1-flash")
    p.add_argument("--key-env", default="OPENCODE_GO_API_KEY")
    p.add_argument("--session", default="herness-live")
    p.add_argument("--steps", type=int, default=6)
    p.add_argument("--cwd")
    p.set_defaults(func=cmd_live)

    p = sub.add_parser("record", help="записать событие в журнал прогона")
    p.add_argument("--run", required=True)
    p.add_argument("--type", default="note")
    p.add_argument("--payload")
    p.add_argument("--artifact")
    p.add_argument("--call-id", default="cli")
    p.add_argument("--preview")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("budget", help="потрачено в прогоне: шаги, время, объём")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_budget)

    p = sub.add_parser("step", help="выполнить команду и записать её в журнал")
    p.add_argument("--run", required=True)
    p.add_argument("command", nargs="?", help="команда (позиционно, без флагов)")
    p.add_argument("--task")
    p.add_argument("--cwd")
    p.add_argument("--start", action="store_true", help="открыть прогон этим шагом")
    p.add_argument("--max-steps", type=int, default=0, help="потолок шагов в прогоне")
    p.add_argument("--max-seconds", type=float, default=0, help="потолок времени прогона")
    p.add_argument("--max-bytes", type=int, default=0, help="потолок объёма артефактов")
    p.set_defaults(func=cmd_step)

    p = sub.add_parser("report", help="собрать report.md из журнала")
    p.add_argument("--run", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--boundary", nargs="*")
    p.add_argument("--claim", nargs="*")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("plan", help="раскладка запроса на типы и уровень")
    p.add_argument("request", nargs="?")
    p.add_argument("--stats", action="store_true", help="точность распознавания на журналах")
    p.add_argument("--compare", action="store_true", help="насколько правила отличаются от всегда-L1")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("ping", help="живая проверка провайдера")
    p.add_argument("--base", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--key-env", default="OPENCODE_API_KEY")
    p.add_argument("--no-stream", action="store_true")
    p.add_argument("--session", help="id разговора для x-opencode-session")
    p.set_defaults(func=cmd_ping)

    p = sub.add_parser("gates", help="секреты, утверждения, ссылки")
    p.add_argument("--root", default=str(ROOT))
    p.set_defaults(func=cmd_gates)

    p = sub.add_parser("refs", help="справочник: репозитории и внешние источники")
    p.add_argument("action", choices=["sync", "search", "list", "add", "watch"])
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






