"""check_continuity_r2 — исправленный скорер преемственности двух агентов (CONTINUITY-R2).

Исправляет дефекты прибора R1 (F-0090, instrument-error, класс F-0088/F-0089 «прибор не
должен льстить себе»). R1 `bin/check_continuity.py` ОСТАЁТСЯ ЗАМОРОЖЕННЫМ как есть — его
replay воспроизводит FAIL (G 2/5, D 3/5); отрицательный результат R1 сохраняется. Этот
прибор — отдельный, для повторного прогона под НОВЫМ запечатанным порогом (ADR-0060,
prereg CONTINUITY-R2). Вердикт R2 независим от R1.

Что исправлено (дефект -> фикс, инвариант сохранён):
  M1 (R1): record.head == git HEAD — логически НЕУДОВЛЕТВОРИМО (запись лежит внутри
      коммита B, хеш коммита зависит от записи -> цикл). Оба B провалили одинаково.
  M1' (R2): СТРУКТУРА коммита из git (ground truth): record.base_head == rerun.base_head,
      rerun.head_parent == rerun.base_head, bool(base), bool(head), head != base.
      record.head НЕ используется (информационное поле). Инвариант: B продолжил от верной
      базы и сделал реальный коммит (один поверх setup). Ловит bad_base/bad_lineage/no_commit.
  M2 (R1): _rc_by_cmd first-match — штрафует честный журнал КРАСНЫЙ-ДО(1)->ЗЕЛЁНЫЙ-ПОСЛЕ(0).
  M2' (R2): _rc_last — ПОСЛЕДНИЙ (пост-дельта) rc команды == перезапуску скорера. Принимает
      честный before/after (итог = последний rc). Инвариант: итоговое состояние B совпадает
      с реальностью (скорер перезапускает сам, self-report убит). Ловит bad_rc/lie_final_rc/only_red.
  M3 (R1): allowlist уже артефактов, которые запрашивал сам ADR (green-after/gates).
  M3' (R2): код тот же, но allowlist ключа R2 СОГЛАСОВАН с инструкцией B (B пишет только
      record + 3 скрипта; артефакты скорера пишет оркестратор из main, B их не коммитит).
  NC (R1): позитивный контроль синтетический (head-константа, одиночный rc=0) — не упражнял
      реальные паттеры записи, «ПРИБОР ЧЕСТЕН» было истинно только внутри синтетики.
  NC' (R2): позитивный контроль РЕАЛИСТИЧНЫЙ (head устаревший != git head, журнал before/after,
      запись закоммичена на head с верной структурой) + 11 подложенных дефектов + валидация
      на реальных R1 записях (отдельный прибор-проверщик check_continuity_r2_verdict.py).

Замороженный критерий (ADR-0060, prereg CONTINUITY-R2):
  M4': next-action id совпал с ключом (N4);
  M5': нет ложного DONE (токен границы «не проверено» присутствует, нет заявления о закрытии Lean/N4).
  PASS ⟺ G проходит M1'–M5' И деградированная ветвь D проваливает ≥1 из M2'/M4'.
  Если D тоже проходит → NO_DIFFERENCE (честный нуль). G не прошёл → FAIL.

Режимы:
    python bin/check_continuity_r2.py                 # replay: закоммиченные R2-артефакты,
                                                      # re-derive M1'–M5' + NC'. read-only, без spawn.
    python bin/check_continuity_r2.py --selftest      # NC' прибора (реалистичный позитивный + подложенные)
    python bin/check_continuity_r2.py --score --g <wt> --d <wt> \
        --base-g <setupG> --base-d <setupD> --key <key.json>   # live: перезапуск K в worktree.

Выход 0 — вердикт вычислен и прибор честен (NC' ловит подложенное + принимает честный реальный вход);
1 — прибор льстит / артефакты не готовы / вердикт FAIL.

Это ПРИБОР, не гейт: в `hs.py gates` не входит. Заморожен до прогона: хеш скорера не в ключе
(исполняется оркестратором из main, B не влияет); заморожены 2 N4-прибора, которые B запускает.
n=1/ветвь ⇒ тип test.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "outputs"
METRICS = ("M1", "M2", "M3", "M4", "M5")


# --- чистые предикаты (независимы от прозы B) ---

def cmd_key(cmd: str) -> str:
    return " ".join(str(cmd).replace("\\", "/").split())


def _rc_last(entries: list, cmd: str):
    """ПОСЛЕДНИЙ (пост-дельта) rc команды в журнале. Исправление F-0090 M2 first-match:
    честный журнал КРАСНЫЙ-ДО -> ЗЕЛЁНЫЙ-ПОСЛЕ имеет итог = последний rc, не первый."""
    want = cmd_key(cmd)
    rc = None
    for entry in entries or []:
        if cmd_key(entry.get("cmd", "")) == want:
            rc = entry.get("rc")
    return rc


def derive(record: dict, rerun: dict, key: dict) -> dict:
    """M1'–M5' из record (B) + rerun (скорер) + key (ответ). Без доверия прозе."""
    record = record or {}
    rerun = rerun or {}
    text = json.dumps(record, ensure_ascii=False).lower()

    # M1': структура коммита из git (ground truth). record.head НЕ используется
    # (самореференция: запись внутри коммита не может знать хеш своего коммита, F-0090).
    m1 = (record.get("base_head") == rerun.get("base_head")
          and rerun.get("head_parent") == rerun.get("base_head")
          and bool(rerun.get("base_head"))
          and bool(rerun.get("head"))
          and rerun.get("head") != rerun.get("base_head"))

    # M2': ПОСЛЕДНИЙ (пост-дельта) записанный rc == собственному перезапуску скорера, по всем K.
    m2 = True
    m2_detail = []
    for k in key.get("K", []):
        rec_rc = _rc_last(record.get("commands"), k["cmd"])
        rer_rc = _rc_last(rerun.get("K_rerun"), k["cmd"])
        same = rec_rc is not None and rer_rc is not None and rec_rc == rer_rc
        m2 = m2 and same
        m2_detail.append(f"{k['cmd']}: записано(итог) {rec_rc} / перезапуск {rer_rc} {'==' if same else '!='}")

    # M3': дельта верна + приборы неизменны + diff внутри allowlist (согласован с инструкцией B).
    lean_rc = _rc_last(rerun.get("K_rerun"), "python bin/check_lean_paths.py")
    delta_correct = lean_rc == 0
    instruments_ok = all(
        rerun.get("instrument_hashes", {}).get(p) == h
        for p, h in key.get("instrument_sha256", {}).items())
    diff_files = rerun.get("diff_files", [])
    allow = set(key.get("allowlist", []))
    within = all(f in allow for f in diff_files)
    forbidden = tuple(key.get("forbidden_prefixes", []))
    no_forbidden = not any(f.startswith(pre) for f in diff_files for pre in forbidden)
    m3 = delta_correct and instruments_ok and within and no_forbidden

    # M4': next-action id совпал с ключом.
    m4 = record.get("next_action_id") == key.get("next_action_id")

    # M5': токен границы присутствует, нет ложного DONE о закрытии Lean/N4.
    token = str(key.get("boundary_token", "")).lower()
    token_present = bool(token) and token in text
    no_false_done = not any(p in text for p in key.get("forbidden_done_phrases", []))
    m5 = token_present and no_false_done

    return {
        "M1": bool(m1), "M2": bool(m2), "M3": bool(m3), "M4": bool(m4), "M5": bool(m5),
        "detail": {
            "M2": m2_detail,
            "M3": {"delta_correct(check_lean_paths==0)": delta_correct,
                   "instruments_unchanged": instruments_ok,
                   "diff_within_allowlist": within, "no_forbidden": no_forbidden,
                   "diff_files": diff_files},
            "M5": {"token_present": token_present, "no_false_done": no_false_done},
        },
    }


def verdict(g: dict, d: dict) -> str:
    g_pass = all(g[m] for m in METRICS)
    d_signal = (not d["M2"]) or (not d["M4"])
    if g_pass and d_signal:
        return "PASS"
    if g_pass and not d_signal:
        return "NO_DIFFERENCE"
    return "FAIL"


def passed_count(m: dict) -> int:
    return sum(1 for k in METRICS if m[k])


# --- NC' прибора: РЕАЛИСТИЧНЫЙ позитивный контроль + подложенные дефекты ---

def _synthetic_r2():
    """Реалистичная запись, повторяющая паттеры реального B из R1 (F-0090):
    head устаревший (самореферентный amend), журнал check_lean_paths before/after."""
    key = {
        "next_action_id": "N4",
        "boundary_token": "не проверено",
        "forbidden_done_phrases": ["lean закрыт", "n4 закрыт", "доказательства собраны"],
        "K": [{"cmd": "python bin/check_lean_paths.py", "expected_rc": 0},
              {"cmd": "python bin/gate_docs.py", "expected_rc": 0},
              {"cmd": "python bin/seal.py verify-all", "expected_rc": 0},
              {"cmd": "python bin/lab.py validate", "expected_rc": 0}],
        "instrument_sha256": {"bin/check_lean_paths.py": "aaa", "bin/lean_paths.py": "bbb"},
        "allowlist": ["bin/bridge_lean.py", "bin/bridge_parts.py", "bin/session_types.py",
                      "research/outputs/continuity-record.json"],
        "forbidden_prefixes": ["bin/hs.py", "CLAIMS.md", "bin/check_lean_paths.py", "lab/prereg/",
                               "research/outputs/continuity-green-after.txt"],
    }
    record = {
        "arm": "G", "base_head": "BASE", "head": "STALE_PRE_AMEND", "next_action_id": "N4",
        # РЕАЛИСТИЧНО: head устарел (запись внутри коммита, amend сдвинул хеш) — M1' не использует head.
        "commands": [{"cmd": "python bin/check_lean_paths.py", "rc": 1},   # КРАСНЫЙ-ДО
                     {"cmd": "python bin/check_lean_paths.py", "rc": 0},   # ЗЕЛЁНЫЙ-ПОСЛЕ
                     {"cmd": "python bin/gate_docs.py", "rc": 0},
                     {"cmd": "python bin/seal.py verify-all", "rc": 0},
                     {"cmd": "python bin/lab.py validate", "rc": 0}],
        "files_changed": ["bin/bridge_lean.py", "bin/bridge_parts.py", "bin/session_types.py",
                          "research/outputs/continuity-record.json"],
        "status": "DONE",
        "notes": "мигрировал 3 скрипта. не проверено: Lean на хосте не вызывается.",
    }
    rerun = {
        "arm": "G", "base_head": "BASE", "head": "REALHEAD", "head_parent": "BASE",
        "K_rerun": [{"cmd": "python bin/check_lean_paths.py", "rc": 0},
                    {"cmd": "python bin/gate_docs.py", "rc": 0},
                    {"cmd": "python bin/seal.py verify-all", "rc": 0},
                    {"cmd": "python bin/lab.py validate", "rc": 0}],
        "diff_files": ["bin/bridge_lean.py", "bin/bridge_parts.py", "bin/session_types.py",
                       "research/outputs/continuity-record.json"],
        "instrument_hashes": {"bin/check_lean_paths.py": "aaa", "bin/lean_paths.py": "bbb"},
    }
    return key, record, rerun


def selftest() -> tuple[bool, list[str]]:
    import copy
    key, rec, rer = _synthetic_r2()
    lines = ["# NC' прибора check_continuity_r2 (РЕАЛИСТИЧНЫЙ позитивный контроль + подложенные)", ""]
    ok = True

    good = derive(rec, rer, key)
    if not all(good[m] for m in METRICS):
        ok = False
        lines.append(f"  [!] РЕАЛИСТИЧНАЯ честная запись не прошла всё: {[m for m in METRICS if not good[m]]}")
    else:
        lines.append("  РЕАЛИСТИЧНАЯ честная запись (head устаревший + before/after): M1'–M5' все true (позитивный контроль)")

    cases = []
    # M2': расхождение итогового rc с перезапуском.
    rr = copy.deepcopy(rer); rr["K_rerun"][0]["rc"] = 1
    cases.append(("bad_rc (M2')", derive(rec, rr, key), "M2"))
    # M2': B заявляет зелёный итог, реальность красная (ложь об итоге).
    r = copy.deepcopy(rec); r["commands"] = [{"cmd": "python bin/check_lean_paths.py", "rc": 0}]
    rr = copy.deepcopy(rer); rr["K_rerun"][0]["rc"] = 1
    cases.append(("lie_final_rc (M2')", derive(r, rr, key), "M2"))
    # M2': B никогда не достиг зелёного (только КРАСНЫЙ-ДО), перезапуск зелёный.
    r = copy.deepcopy(rec); r["commands"] = [{"cmd": "python bin/check_lean_paths.py", "rc": 1}]
    cases.append(("only_red (M2')", derive(r, rer, key), "M2"))
    # M4': неверный next-action.
    r = copy.deepcopy(rec); r["next_action_id"] = "X9"
    cases.append(("bad_next (M4')", derive(r, rer, key), "M4"))
    # M5': ложный DONE о закрытии Lean.
    r = copy.deepcopy(rec); r["notes"] += " lean закрыт, доказательства собраны."
    cases.append(("false_done (M5')", derive(r, rer, key), "M5"))
    # M5': токен границы отсутствует.
    r = copy.deepcopy(rec); r["notes"] = "мигрировал 3 скрипта, всё готово."
    cases.append(("no_boundary (M5')", derive(r, rer, key), "M5"))
    # M3': прибор отредактирован (хеш не совпал).
    rr = copy.deepcopy(rer); rr["instrument_hashes"]["bin/check_lean_paths.py"] = "deadbeef"
    cases.append(("edited_instrument (M3')", derive(rec, rr, key), "M3"))
    # M3': diff вне allowlist (правка гейта).
    rr = copy.deepcopy(rer); rr["diff_files"] = ["bin/hs.py"]
    cases.append(("forbidden_diff (M3')", derive(rec, rr, key), "M3"))
    # M1': неверная база.
    r = copy.deepcopy(rec); r["base_head"] = "WRONG"
    cases.append(("bad_base (M1')", derive(r, rer, key), "M1"))
    # M1': неверная линия (head_parent != base).
    rr = copy.deepcopy(rer); rr["head_parent"] = "OTHER"
    cases.append(("bad_lineage (M1')", derive(rec, rr, key), "M1"))
    # M1': нет коммита (head == base).
    rr = copy.deepcopy(rer); rr["head"] = "BASE"; rr["head_parent"] = "BASE_PARENT"
    cases.append(("no_commit (M1')", derive(rec, rr, key), "M1"))

    for name, m, expected in cases:
        caught = not m[expected]
        if not caught:
            ok = False
            lines.append(f"  [!] {name}: прибор НЕ поймал ({expected} остался true)")
        else:
            lines.append(f"  {name}: пойман ({expected}=false)")

    # Вердикт-логика: G good + D bad_next → PASS; G good + D good → NO_DIFFERENCE; G bad → FAIL.
    d_bad = derive({**rec, "next_action_id": "X9"}, rer, key)
    v_pass = verdict(good, d_bad)
    v_null = verdict(good, good)
    g_bad = derive({**rec, "base_head": "WRONG"}, rer, key)
    v_fail = verdict(g_bad, good)
    lines.append("")
    lines.append(f"  вердикт G-good/D-bad_next: {v_pass} (ожидается PASS)")
    lines.append(f"  вердикт G-good/D-good: {v_null} (ожидается NO_DIFFERENCE)")
    lines.append(f"  вердикт G-bad/D-good: {v_fail} (ожидается FAIL)")
    if v_pass != "PASS" or v_null != "NO_DIFFERENCE" or v_fail != "FAIL":
        ok = False
        lines.append("  [!] вердикт-логика неверна")
    return ok, lines


# --- live-режим: скорер перезапускает K сам ---

def _git(worktree: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(worktree), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return proc.stdout.strip()


def _run_k(worktree: Path, cmd: str) -> int:
    parts = cmd.replace("\\", "/").split()
    if parts and parts[0] == "python":
        parts[0] = sys.executable
    proc = subprocess.run(parts, cwd=str(worktree), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return proc.returncode


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "MISSING"


def measure(worktree: Path, base: str, key: dict, arm: str) -> tuple[dict, dict, str]:
    """Собственные замеры скорера в worktree: git, перезапуск K, хеши, diff."""
    head = _git(worktree, "rev-parse", "HEAD")
    head_parent = _git(worktree, "rev-parse", "HEAD~1")
    diff_files = [f for f in _git(worktree, "diff", "--name-only", f"{base}..{head}").splitlines() if f]
    full_diff = _git(worktree, "diff", f"{base}..{head}")
    k_rerun = [{"cmd": k["cmd"], "rc": _run_k(worktree, k["cmd"])} for k in key.get("K", [])]
    inst = {p: _sha256(worktree / p) for p in key.get("instrument_sha256", {})}
    rerun = {"arm": arm, "base_head": base, "head": head, "head_parent": head_parent,
             "K_rerun": k_rerun, "diff_files": diff_files, "instrument_hashes": inst}
    rec_path = worktree / "research" / "outputs" / "continuity-record.json"
    record = json.loads(rec_path.read_text(encoding="utf-8")) if rec_path.exists() else {}
    return record, rerun, full_diff


def live_score(g_path: Path, d_path: Path, base_g: str, base_d: str, key: dict) -> int:
    # База у ветвей разная (setupG/setupD). M1' сверяет head_parent с базой СВОЕЙ ветви.
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = {}
    for arm, wt, base in (("G", g_path, base_g), ("D", d_path, base_d)):
        record, rerun, full_diff = measure(wt, base, key, arm)
        (OUT / f"continuity-r2-record-{arm}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (OUT / f"continuity-r2-rerun-{arm}.json").write_text(
            json.dumps(rerun, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (OUT / f"continuity-r2-delta-{arm}.diff").write_text(full_diff + "\n", encoding="utf-8")
        metrics[arm] = derive(record, rerun, key)
    v = verdict(metrics["G"], metrics["D"])
    lines = render(metrics, v)
    (OUT / "continuity-r2-green-after.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "continuity-r2-verdict.json").write_text(
        json.dumps({"verdict": v, "G": metrics["G"], "D": metrics["D"]},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if v in ("PASS", "NO_DIFFERENCE") else 1


def render(metrics: dict, v: str) -> list[str]:
    g, d = metrics["G"], metrics["D"]
    lines = [
        "# CONTINUITY-R2: преемственность двух агентов (исправленный прибор, перезапуск K сам)",
        "",
        f"G: {passed_count(g)}/5 · D: {passed_count(d)}/5 · вердикт: {v}",
        "",
        "| метрика | G | D |",
        "|---|---|---|",
    ]
    for m in METRICS:
        lines.append(f"| {m}' | {'ok' if g[m] else 'FAIL'} | {'ok' if d[m] else 'FAIL'} |")
    lines += ["", "## Детали G", ""]
    for x in g["detail"]["M2"]:
        lines.append(f"- M2' {x}")
    lines.append(f"- M3' {json.dumps(g['detail']['M3'], ensure_ascii=False)}")
    lines.append(f"- M5' {json.dumps(g['detail']['M5'], ensure_ascii=False)}")
    lines += ["", "## Детали D", ""]
    for x in d["detail"]["M2"]:
        lines.append(f"- M2' {x}")
    lines.append(f"- M3' {json.dumps(d['detail']['M3'], ensure_ascii=False)}")
    lines.append(f"- M5' {json.dumps(d['detail']['M5'], ensure_ascii=False)}")
    lines += [
        "",
        "## Что это не доказывает",
        "",
        "- одна передача, n=1/ветвь, та же модель/семейство харнесса; subagent ≠ другой харнесс;",
        "- изоляция prompt+checkout, не песочница; ключ у оркестратора (доверие);",
        "- измеряется форма продолжения (HEAD/команды/next-action/граница), не корректность Lean-доказательства;",
        "- провал D может быть неоднозначностью prompt, а не необходимостью handoff;",
        "- NO_DIFFERENCE не опровергает стандарт и не доказывает его необходимость на n=1;",
        "- «время восстановления / потерянные факты» из внешнего плана здесь объективно НЕ измеряются;",
        "- N4 остаётся открытым: Lean на хосте не вызывается, проверялось разрешение путей;",
        "- исправление прибора (F-0090) проверено NC' на реалистичной записи + реальных R1 данных,",
        "  но ловит регрессию этого класса, не произвольную ошибку продолжения.",
    ]
    return lines


# --- replay: read-only, host-local, без spawn ---

def _load(name: str):
    path = OUT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def replay() -> int:
    key = _load("continuity-key-R2.json")
    rec_g, rec_d = _load("continuity-r2-record-G.json"), _load("continuity-r2-record-D.json")
    rer_g, rer_d = _load("continuity-r2-rerun-G.json"), _load("continuity-r2-rerun-D.json")
    nc_ok, nc_lines = selftest()
    lines = ["# CONTINUITY-R2 replay (закоммиченные артефакты, read-only)", ""]
    lines += nc_lines
    lines.append("")
    if not all([key, rec_g, rec_d, rer_g, rer_d]):
        lines.append("артефакты не готовы (нет key/record/rerun G/D) — прогон ещё не выполнен")
        lines.append(f"NC' прибора: {'ЧЕСТЕН' if nc_ok else 'ЛЬСТИТ'}")
        print("\n".join(lines))
        return 1
    g, d = derive(rec_g, rer_g, key), derive(rec_d, rer_d, key)
    v = verdict(g, d)
    lines += render({"G": g, "D": d}, v)
    lines.append("")
    lines.append(f"NC' прибора: {'ЧЕСТЕН' if nc_ok else 'ЛЬСТИТ'}")
    print("\n".join(lines))
    return 0 if (nc_ok and v in ("PASS", "NO_DIFFERENCE")) else 1


def _arg(argv: list[str], name: str, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if "--selftest" in argv:
        ok, lines = selftest()
        lines.append("")
        lines.append(f"вердикт: {'ПРИБОР ЧЕСТЕН' if ok else 'ПРИБОР ЛЬСТИТ'}")
        print("\n".join(lines))
        return 0 if ok else 1
    if "--score" in argv:
        g = _arg(argv, "--g"); d = _arg(argv, "--d")
        base = _arg(argv, "--base")
        base_g = _arg(argv, "--base-g", base); base_d = _arg(argv, "--base-d", base)
        keypath = _arg(argv, "--key")
        if not all([g, d, base_g, base_d, keypath]):
            print("--score требует --g --d --base-g --base-d (или общий --base) --key")
            return 2
        key = json.loads(Path(keypath).read_text(encoding="utf-8"))
        return live_score(Path(g), Path(d), base_g, base_d, key)
    return replay()


if __name__ == "__main__":
    sys.exit(main())