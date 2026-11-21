"""lean_wsl — исполнитель WSL lake rc2: динамическая проверка Lean-контура (N4 proof-side).

Хост Windows не имеет Lean (`~/.elan` отсутствует, `lean`/`lake` не на PATH), поэтому
`bin/lean_check.py` на хосте возвращает 2 («нет Lean»). Toolchain **rc2** установлен в
WSL Ubuntu (`/root/.elan`). Этот исполнитель вызывает WSL `lake`/`lean` rc2 на репо
`proofs/` (путь берётся из резолвера `bin/lean_paths.py`), превращая N4 из статической
проверки путей (`check_lean_paths`) в динамическую сборку доказательств.

    python bin/lean_wsl.py   # агрегат Proofs + контуры + аксиомы + оба отрицательных контроля

Зеркалит `lean_check.py`: `lake build Proofs.Policy` обязан собраться; аксиомы теорем —
только три стандартные; `lake build Proofs.Negative` обязан УПАСТЬ (иначе проверка пуста).

Fail-closed: нет WSL / нет toolchain rc2 / нет proofs → exit 2/3, не молчаливый зелёный.
Артефакт: `research/outputs/lean-wsl-check.txt`. Scratch-проба пишется в /tmp WSL,
отслеживаемый `proofs/Probe.lean` НЕ трогается.

Граница: доказывается свойство моделей, а не соответствие Rust-кода моделям.
F-0080 закрыт (ADR-0061): модели разведены по namespace Policy/PartBridge, агрегат собирается.
Исполнитель host-only: в CI (ubuntu-latest) WSL нет, поэтому это НЕ CI-гейт.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bin.lean_paths import proofs_dir, lean_toolchain, _normalize_toolchain  # noqa: E402

PROOFS = proofs_dir()
OUT = ROOT / "research" / "outputs" / "lean-wsl-check.txt"
DISTRO = "Ubuntu"
THEOREMS = [
    "Policy.deny_beats_allow",
    "Policy.deny_means_not_allowed",
    "Policy.no_allow_means_denied",
    "Policy.empty_policy_denies",
    "Policy.mediator_refuses",
    "Policy.mediator_performs",
]
STANDARD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
BRIDGE_THEOREMS = [
    "PartBridge.no_bridge_of_incompatible",
    "PartBridge.hasDeny_append_left",
    "PartBridge.hasDeny_append_right",
    "PartBridge.deny_survives",
    "PartBridge.bridge_allow_no_deny",
]
COMPOSITION_THEOREMS = [
    "Composition.comp_within",
    "Composition.leak_created_by_composition",
    "Composition.runChain_refuses_leak",
    "Composition.runChain_performs_safe",
    "Composition.unproven_refused",
    "Composition.chainOk_all_proven",
]


def to_wsl(p: Path) -> str:
    """Windows-путь → WSL /mnt/<drive>/... (C:\\111\\harness\\proofs → /mnt/c/111/harness/proofs)."""
    s = str(p)
    if len(s) >= 2 and s[1] == ":":
        return f"/mnt/{s[0].lower()}" + s[2:].replace("\\", "/")
    return s.replace("\\", "/")


def run_wsl(bash_cmd: str, timeout: int = 600) -> tuple[int, str]:
    """subprocess со списком аргументов (без shell): строка доходит до WSL bash literally,
    поэтому $?/heredoc не перехватываются внешним shell и rc надёжен."""
    try:
        proc = subprocess.run(
            ["wsl.exe", "-d", DISTRO, "--", "bash", "-c", bash_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError:
        return 127, "wsl.exe не найден"
    except subprocess.TimeoutExpired:
        return 124, f"timeout {timeout}s"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    lines = ["# Динамическая проверка Lean-контура через WSL rc2 (N4 proof-side, F-0080)", ""]

    # 1. WSL доступен?
    rc, out = run_wsl("echo wsl-ok", timeout=90)
    if rc != 0 or "wsl-ok" not in out:
        print(f"нет WSL {DISTRO} (rc={rc}) — исполнитель недоступен, fail-closed")
        return 2

    # 2. toolchain rc2 в WSL?
    tc = _normalize_toolchain(lean_toolchain())
    wsl_proofs = to_wsl(PROOFS)
    rc, out = run_wsl(f'test -x "$HOME/.elan/toolchains/{tc}/bin/lake" && echo tc-ok', timeout=90)
    if rc != 0 or "tc-ok" not in out:
        print(f"нет toolchain {tc} в WSL (rc={rc}) — fail-closed")
        return 2

    elan_bin = f"$HOME/.elan/toolchains/{tc}/bin"
    base = (f'cd "{wsl_proofs}" && export PATH="{elan_bin}:$PATH" '
            f'&& export LEAN_PATH="{wsl_proofs}/.lake/build/lib/lean"')
    lines += [f"proofs (резолвер): `{PROOFS}`", f"WSL: `{wsl_proofs}`, toolchain: `{tc}`", ""]

    # 3. агрегат Proofs обязан собраться (F-0080: коллизия имён видна только здесь)
    rc, text = run_wsl(f"{base} && lake build")
    ok_aggregate = rc == 0
    lines.append(f"## Агрегат Proofs: {'СОБРАН (rc=0)' if ok_aggregate else f'НЕ СОБРАН (rc={rc})'}")
    for ln in text.splitlines():
        if "error" in ln.lower() or "already contains" in ln or "Build completed" in ln:
            lines.append(f"   {ln.strip()}")
    lines.append("")

    # 4. контуры поодиночке (зеркало lean_check / bridge_parts)
    rc, _ = run_wsl(f"{base} && lake build Proofs.Policy")
    ok_proof = rc == 0
    lines.append(f"## Контур политики: {'СОБРАН (rc=0)' if ok_proof else f'НЕ СОБРАН (rc={rc})'}")
    lines.append("")
    rc, _ = run_wsl(f"{base} && lake build Proofs.PartBridge")
    ok_bridge = rc == 0
    lines.append(f"## Контур моста частей: {'СОБРАН (rc=0)' if ok_bridge else f'НЕ СОБРАН (rc={rc})'}")
    lines.append("")
    rc, _ = run_wsl(f"{base} && lake build Proofs.Composition")
    ok_composition = rc == 0
    lines.append(f"## Контур композиции K9: {'СОБРАН (rc=0)' if ok_composition else f'НЕ СОБРАН (rc={rc})'}")
    lines.append("")

    # 5. аксиомы теорем — только стандартные (scratch в /tmp, репо Probe.lean не трогаем)
    all_theorems = THEOREMS + BRIDGE_THEOREMS + COMPOSITION_THEOREMS
    probe_body = ("import Proofs.Policy\nimport Proofs.PartBridge\nimport Proofs.Composition\n"
                  + "\n".join(f"#print axioms {t}" for t in all_theorems) + "\n")
    ax_cmd = (f"{base} && cat > /tmp/ProbeWsl.lean <<'EOF'\n{probe_body}EOF\n"
              f"lean /tmp/ProbeWsl.lean\nrc=$?\nrm -f /tmp/ProbeWsl.lean\nexit $rc")
    rc, axioms = run_wsl(ax_cmd)
    lines.append("## Аксиомы каждой теоремы")
    clean = rc == 0
    for ln in axioms.splitlines():
        ln = ln.strip()
        if "depends on axioms" not in ln:
            continue
        name = ln.split("'")[1]
        used = set(ln.split("[")[1].rstrip("]").replace(" ", "").split(","))
        extra = used - STANDARD_AXIOMS
        if extra:
            clean = False
        suffix = f" — НЕСТАНДАРТНЫЕ: {', '.join(sorted(extra))}" if extra else ""
        lines.append(f"- `{name}`: {', '.join(sorted(used))}{suffix}")
    if rc != 0:
        lines.append(f"   проба аксиом не выполнилась (rc={rc})")
    lines.append("")

    # 6. отрицательные контроли обязаны УПАСТЬ (все три)
    rc, text = run_wsl(f"{base} && lake build Proofs.Negative")
    rejected_policy = rc != 0
    lines.append(f"## NC политики (Proofs.Negative): {'отвергнут (rc≠0)' if rejected_policy else 'ПРИНЯТ — ПРОВЕРКА НЕ РАБОТАЕТ'}")
    for ln in text.splitlines():
        if "unsolved goals" in ln:
            lines.append(f"   {ln.strip()}")
    lines.append("")
    rc, text = run_wsl(f"{base} && lake build Proofs.PartBridgeNegative")
    rejected_bridge = rc != 0
    lines.append(f"## NC моста (Proofs.PartBridgeNegative): {'отвергнут (rc≠0)' if rejected_bridge else 'ПРИНЯТ — ПРОВЕРКА НЕ РАБОТАЕТ'}")
    for ln in text.splitlines():
        if "unsolved goals" in ln:
            lines.append(f"   {ln.strip()}")
    lines.append("")
    rc, text = run_wsl(f"{base} && lake build Proofs.CompositionNegative")
    rejected_composition = rc != 0
    lines.append(f"## NC композиции (Proofs.CompositionNegative): {'отвергнут (rc≠0)' if rejected_composition else 'ПРИНЯТ — ПРОВЕРКА НЕ РАБОТАЕТ'}")
    for ln in text.splitlines():
        if "proved that the proposition" in ln or "unsolved goals" in ln:
            lines.append(f"   {ln.strip()}")
    lines.append("")

    verdict = (ok_aggregate and ok_proof and ok_bridge and ok_composition and clean
               and rejected_policy and rejected_bridge and rejected_composition)
    lines.append(f"## Итог: {'агрегат собран, доказательства приняты, ложь отвергнута, аксиомы стандартные' if verdict else 'ЕСТЬ ПРОБЛЕМА'}")
    lines.append("")
    lines.append("Граница: доказаны свойства моделей, не соответствие Rust-кода моделям.")
    lines.append("K9: модель проверяет объявленные замыкания и цепочку мостов; это K9_model_checked, не K9_proven.")
    lines.append("F-0080 закрыт (ADR-0061): namespace Policy/PartBridge, агрегат Proofs собирается.")
    lines.append("N4 proof-side: путь резолвера динамически проверен сборкой rc2 в WSL (не только статика).")
    lines.append("Исполнитель host-only: в CI (ubuntu-latest) WSL нет; сборка в CI требует установки Lean rc2.")

    text_out = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text_out, encoding="utf-8")
    print(text_out)
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())