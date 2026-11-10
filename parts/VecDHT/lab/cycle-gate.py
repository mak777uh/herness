#!/usr/bin/env python3
"""Гейт круга: боль -> источники -> решение по рубрике Lean -> только потом оракул.

Причина появления. Контур источников (`ADR-0045`) и Lean (`lab/lean/`) существовали, но держались
на памяти агента: за пять циклов `H-0085`…`H-0091` не добавлено ни одной формальной модели,
в индексе не появилось ни одной записи о чужой кодовой реализации, а `lab/lean/` не проверялся
с момента его создания. Слово владельца 2026-10-23: механизм обязан применяться автоматически,
в том числе к агенту, который открыл репозиторий первым разом. Значит — не абзац в README,
а nonzero exit перед пре-регистрационным коммитом.

Команды:
  python lab/cycle-gate.py H-XXXX         — жёсткая проверка карточки перед пре-регистрацией
  python lab/cycle-gate.py audit -n N     — отчёт по последним N карточкам (кто под правилом)
  python lab/cycle-gate.py --selftest     — посаженные карточки: механизм обязан их отбить

Выход: 0 — круг оформлен, 1 — нарушено правило, 2 — карточка не найдена или прибор негоден.

Карточка обязана содержать (YAML-шапка): id, claim, falsifier, oracle, prior_art, lean.
Формат шапки:

  prior_art: ["L-0007", "L-0008"]        # либо ["не искали — <причина>"]
  prior_art_no_code: "<причина, почему чужой код не читали>"   # опционально
  lean:
    решение: применён                    # применён | не применён
    причина: "<почему>"
    модель: lab/lean/VecDHT/Denylist.lean
    пространство: да                     # четыре вопроса рубрики: да | нет
    без_времени: да
    для_всех: да
    дешевле_стенда: нет

Рубрика (`lab/lean-rubric.md`) отвечает не «нравится ли мне Lean», а «конечно ли пространство
и безвременно ли утверждение»: четыре «да» делают модель обязательной, и gate проверяет её
компиляцией и отсутствием `sorry`.
"""

import argparse
import glob
import io
import json
import os
import re
import shutil
import subprocess
import historylib  # ADR-0079: полнота истории спрашивается до первого числа
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.environ.get("VEC_DHT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "lab", "library", "index.jsonl")
LEAN_DIR = os.path.join(ROOT, "lab", "lean", "VecDHT")
REQUIRED_KEYS = ("id", "claim", "falsifier", "oracle", "prior_art", "lean")

# Карточка эксперимента: то, что обязано быть заморожено до первого прогона (шаг 2 жизненного
# цикла в `lab/README.md`). `hypothesis` сверяется с id карточки отдельно.
EXPERIMENT_KEYS = ("threshold", "environment", "command", "base_commit")
# Точное совпадение, не подстрока: «не применён» содержит «применён», и проверка на подстроку
# превращала отказ в согласие (самопроверка selftest, случай «отказ при четырёх да»).
LEAN_APPLIED = ("применён", "применен", "сделан", "есть")
LEAN_SKIPPED = ("не применён", "не применен", "не применим", "неприменим", "не сделан", "не нужен")
# Карточки без ключа `lean:` созданы до механизма (2026-10-23) и не считаются нарушением —
# но в отчёте они помечены явно, чтобы «историч.» нельзя было принять за «проверено».
PRE_MECHANISM_NOTE = "историческая карточка (до механизма ADR-0048)"


def card_path(hid):
    hits = sorted(glob.glob(os.path.join(ROOT, "lab", "hypotheses", f"{hid}-*.md")))
    if len(hits) != 1:
        return None, hits
    return hits[0], hits


def front_matter(path):
    import yaml
    text = io.open(path, encoding="utf-8").read()
    parts = text.split("---")
    if len(parts) < 3:
        return None, "в файле нет YAML-шапки между линиями ---"
    try:
        return yaml.safe_load(parts[1]), None
    except Exception as e:
        return None, f"YAML-шапка не разобрана ({type(e).__name__}: {e})"


def load_index():
    rows = []
    if not os.path.isfile(INDEX):
        return rows, "нет индекса источников"
    for line in io.open(INDEX, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                return rows, "индекс содержит неразобранную строку"
    return rows, None


def check_prior_art(fm, rows, hid, bad, say):
    """Шаг круга «источники до эксперимента»: строки обязаны существовать, быть привязаны
    к этой гипотезе и быть начаты не позже её."""
    refs = fm.get("prior_art") or []
    if isinstance(refs, str):
        refs = [refs]
    if not isinstance(refs, list) or not refs:
        bad.append("prior_art пуст: шаг «литература и код до эксперимента» не сделан "
                   "(поиск — `python lab/sources.py hunt`)")
        return
    excuse = [r for r in refs if str(r).startswith("не искали")]
    if excuse:
        if len(str(excuse[0])) < 25:
            bad.append(f"отказ от сверки сформулирован в {len(str(excuse[0]))} знаков — это не причина")
        say(f"ПРИОРАРТ {hid}: отказ от источников с причиной")
        return
    by_id = {r.get("id"): r for r in rows}
    card_date = str(fm.get("date", ""))
    kinds = set()
    for lid in refs:
        r = by_id.get(lid)
        if r is None:
            bad.append(f"prior_art называет {lid}, а в индексе такой строки нет")
            continue
        if hid not in (r.get("targets") or []):
            bad.append(f"{lid}: в targets нет {hid} — запись читают не для этой гипотезы")
        if r.get("status") == "не использован":
            bad.append(f"{lid}: статус «не использован» — строку перечислили, но не прочитали")
        opened = str(r.get("opened", ""))
        if card_date and opened and opened > card_date:
            bad.append(f"{lid}: открыта {opened} позже карточки {card_date} — источник найден "
                       f"после того, как гипотеза уже сформулирована")
        kinds.add(r.get("kind"))
    codeish = {"спека", "реализация"} - {None}
    if kinds and not (kinds & codeish):
        reason = str(fm.get("prior_art_no_code") or "")
        if len(reason) < 25:
            bad.append("ни одной записи класса «спека» или «реализация»: решаем боль, которую "
                       "кто-то уже решал кодом, и не смотрим, как (причина — prior_art_no_code, "
                       "поиск — `python lab/sources.py hunt --github`)")
        else:
            say(f"ПРИОРАРТ {hid}: чужой код не читали, причина записана ({len(reason)} зн.)")
    say("ПРИОРАРТ " + f"{hid}: строк={len(refs)} классы={sorted(k for k in kinds if k)}")


def check_lean(fm, hid, bad, say, skip_lean):
    lean = fm.get("lean")
    if lean is None:
        bad.append(f"нет ключа `lean:` — решение по рубрике не принято, а «не принял» — не ответ")
        return
    if not isinstance(lean, dict):
        bad.append(f"`lean:` обязан быть блоком с полями рубрики, а не строкой ({lean!r})")
        return
    for q in ("пространство", "без_времени", "для_всех", "дешевле_стенда"):
        if str(lean.get(q, "")).strip().lower() not in ("да", "нет"):
            bad.append(f"вопрос рубрики «{q}» без ответа да|нет")
    answers = [str(lean.get(q, "")).strip().lower() == "да"
               for q in ("пространство", "без_времени", "для_всех", "дешевле_стенда")]
    required = all(answers)
    dec = str(lean.get("решение", "")).strip().lower()
    applied = dec in LEAN_APPLIED
    skipped = dec in LEAN_SKIPPED
    if not applied and not skipped:
        bad.append(f"`lean.решение`={dec!r} вне словаря применён|не применён")
    reason = str(lean.get("причина", "")).strip()
    if skipped:
        if required:
            bad.append("рубрика дала четыре «да», а модель не сделана: по `lab/lean-rubric.md` "
                       "в этом случае модель обязательна (конечное пространство, ∀-утверждение, "
                       "без времени)")
        if len(reason) < 25:
            bad.append(f"`lean.причина` отказа короче 25 знаков ({len(reason)})")
        say(f"LEAN {hid}: модель не сделана, рубрика обязательной не требует"
            if not required else f"LEAN {hid}: НАРУШЕНИЕ — рубрика требует модель")
        return
    model = str(lean.get("модель", "")).strip()
    if not model:
        bad.append("`lean.решение`=применён, а `lean.модель` не названа")
        return
    path = model if os.path.isabs(model) else os.path.join(ROOT, model)
    if not os.path.isfile(path):
        bad.append(f"модель {model} не найдена на диске")
        return
    text = io.open(path, encoding="utf-8").read()
    if re.search(r"\bsorry\b", text):
        bad.append(f"модель {model} содержит sorry — это незакрытая цель, а не проверка")
    # Рубрика Lean (`lab/lean-rubric.md`, три уровня) обещала машинную проверку двух полей, но до
    # `H-0097` это была цитата в тексте: гейт требовал модель и `sorry`, а не спрашивал, что именно
    # доказано и чем скреплено соответствие модели и кода. Без первого «применён» означает только
    # «файл существует», без второго — уровень 1 молча выдаётся за уровень 2.
    proves = str(lean.get("доказывает", "")).strip()
    if len(proves) < 25:
        bad.append("`lean.доказывает` не назван или короче 25 знаков "
                   f"({len(proves)}) — «доказано» без предмета не ответ (уровень 1 рубрики)")
    corr = str(lean.get("соответствие_кода", "")).strip()
    if not corr:
        bad.append("`lean.соответствие_кода` не назван: без прибора соответствие модели и кода "
                   "считается непроверенным, и это обязано быть записано, а не угадано")
    elif "не проверено" in corr:
        say(f"LEAN {hid}: соответствие модели и кода не проверено — clause на месте")
    else:
        refs = re.findall(r"[A-Za-z0-9_./\\-]+\.(?:rs|sh|py)", corr)
        found = [r for r in refs if os.path.isfile(os.path.join(ROOT, r.replace("\\", "/")))]
        if not refs:
            bad.append("`lean.соответствие_кода` не называет прибор путём (`*.rs|*.sh|*.py`) и не "
                       "говорит «не проверено» — это формулировка, а не проверка (уровень 2)")
        elif not found:
            bad.append(f"прибор соответствия не найден на диске: {refs}")
        else:
            say(f"LEAN {hid}: соответствие скреплено прибором {found[0]}")
    if skip_lean:
        say(f"LEAN {hid}: компиляция пропущена по --skip-lean (в отчёте это НЕ проверка)")
        return
    env = dict(os.environ)
    # Пути тулчейна добавляем только если они есть: жёстко приписанный домашний каталог одного
    # хоста превращал бы проверку чужой машины в «нет Lean», а это другой отказ, чем «модель
    # не компилируется». Если `lean` уже в PATH — ничего не добавляем.
    if shutil.which("lean", path=env.get("PATH", "")) is None:
        extra = [p for p in ("/c/Users/Admin/.elan/bin", os.path.expanduser("~/.elan/bin"),
                             "/c/Users/Admin/mingw64/bin") if os.path.isdir(p)]
        if extra:
            env["PATH"] = os.pathsep.join(extra) + os.pathsep + env.get("PATH", "")
    try:
        p = subprocess.run(["lean", path], capture_output=True, text=True, env=env, timeout=600)
    except FileNotFoundError:
        bad.append("нет тулчейна Lean (elan) — пре-регистрация с моделью невозможна, "
                   "а «не компилировалось» не считается проверкой")
        return
    except subprocess.TimeoutExpired:
        bad.append(f"модель {model} не скомпилировалась за 600 с")
        return
    errs = len([l for l in (p.stdout + p.stderr).splitlines() if "error:" in l])
    if p.returncode != 0 or errs:
        bad.append(f"модель {model} не компилируется (rc={p.returncode}, error:={errs})")
        return
    say(f"LEAN {hid}: модель {os.path.basename(model)} компилируется, sorry=0, ошибок=0")

def check_experiment(hid, bad, say):
    """Карточка эксперимента обязана существовать ДО замера, с порогом и командой.

    Посажено на собственном упущении: пре-регистрация `E-0092` заморозила пороги, фальсификатор,
    helper и PRE_FIX-снимок в `lab/hypotheses/H-0092-*.md`, но файла `lab/experiments/E-0092-*.md`
    в том коммите не было (шаг 2 жизненного цикла `lab/README.md` требует именно его). Гейт это
    не ловил, потому что смотрел только на карточку гипотезы.
    """
    eid = "E-" + hid.split("-")[1]
    hits = sorted(glob.glob(os.path.join(ROOT, "lab", "experiments", eid + "-*.md")))
    if not hits:
        bad.append(f"карточка эксперимента {eid} не найдена — пре-регистрация без неё невозможна")
        return
    fm, err = front_matter(hits[0])
    if fm is None:
        bad.append(f"{os.path.basename(hits[0])}: шапка не разобрана ({err})")
        return
    if str(fm.get("hypothesis", "")).strip() != hid:
        bad.append(f"{os.path.basename(hits[0])}: `hypothesis` не равен {hid}")
    empty = [k for k in EXPERIMENT_KEYS if not str(fm.get(k, "")).strip()]
    if empty:
        bad.append(f"в карточке {eid} не названы: {empty}")
        return
    # Карточка, у которой уже есть вердикт, не может одновременно заявлять, что она ещё
    # пре-регистрируется: `E-0095` закрыли коммитом `2c6a4d6` («закрыт supports»), но в шапке
    # остался `status: pre-registered` при `verdict: "supports"`, и механический перебор 94 карточек
    # нашёл это рассогласование только через цикл `E-0099`. Инвентарь в README и очередь `ADR-0044`
    # читают именно шапку, поэтому такое состояние — не косметика: закрытый круг перестаёт
    # различаться с открытым.
    verdict = str(fm.get("verdict", "")).strip()
    status = str(fm.get("status", "")).strip()
    if verdict in ("supports", "refutes", "satisfies") and status in ("pre-registered", "planned"):
        bad.append(f"{eid}: вердикт `{verdict}` при статусе `{status}` — карточка не переведена "
                   f"в закрытое состояние")
        return
    say(f"E-CARD {eid}: порог, окружение и команда названы")


def cmd_gate(args):
    bad, out = [], []
    say = out.append
    path, hits = card_path(args.hid)
    if path is None:
        print(f"Карточка {args.hid} не найдена (совпадений {len(hits)}): {hits}")
        return 2
    fm, err = front_matter(path)
    if fm is None:
        print(f"CYCLE {args.hid} НЕ_РАЗОБРАНА: {err}")
        return 2
    missing = [k for k in REQUIRED_KEYS if k not in fm]
    if missing:
        bad.append(f"нет обязательных ключей: {missing}")
    rows, idx_err = load_index()
    if idx_err:
        bad.append(f"индекс источников: {idx_err}")
    if not str(fm.get("claim", "")).strip():
        bad.append("claim пуст")
    if not str(fm.get("falsifier", "")).strip():
        bad.append("falsifier пуст — невыполнимая проверка хуже отсутствия проверки "
                   "(ДИАГНОЗ-1 из E-0087)")
    if not str(fm.get("oracle", "")).strip():
        bad.append("oracle не назван")
    check_prior_art(fm, rows, args.hid, bad, say)
    check_lean(fm, args.hid, bad, say, args.skip_lean)
    check_experiment(args.hid, bad, say)
    for line in out:
        print(line)
    for b in bad:
        print(f"  НАРУШЕНИЕ: {b}")
    print(f"CYCLE {args.hid}={'OK' if not bad else 'FAIL'} нарушений={len(bad)}")
    return 0 if not bad else 1


LEGACY_LIST = os.path.join("lab", "cycle-gate-legacy.tsv")
DEFECTS_LIST = os.path.join("lab", "cycle-gate-defects.tsv")
MECH_ADR = "ADR-0048"
MIN_REASON = 25
UNPARSED_CLASS = "не_разобрана"
NO_LEAN_CLASS = "без_рубрики"
# Текст заготовки причины. Для карточки до порога он допустим как есть (дата из git и есть
# причина), для карточки после порога — только как ловушка: сверка красит `АВТОПРИЧИНА`.
AUTO_REASON_OLD = ("нарушения перечисляет `python lab/cycle-gate.py audit --all`; "
                   "причина исправления — отдельный текстовый цикл")
AUTO_REASON_FRESH = ("причину обязан назвать человек: карточка добавлена позже механизма "
                     f"{MECH_ADR}, авто-текст освобождением не считается")


def rel(path):
    """Путь от корня дерева в форме, которую понимает msys-git (обратная косая черта ломает
    pathspec молча: git не находит файл и отвечает пустотой, а пустой ответ читается как
    «карточка не в истории»)."""
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def card_add_ts(relpath):
    """Unix-время первого коммита, добавившего файл; None — файла нет в истории."""
    try:
        p = subprocess.run(["git", "log", "--diff-filter=A", "--format=%at", "--", relpath],
                           capture_output=True, text=True, cwd=ROOT, timeout=120)
    except Exception:
        return None
    lines = [l for l in p.stdout.strip().splitlines() if l.strip()]
    return int(lines[-1]) if lines else None


def iso(ts):
    import time
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def mechanism_ts():
    """Порог механизма — время коммита, добавившего файл ADR-0048, а не дата в её тексте."""
    hits = sorted(glob.glob(os.path.join(ROOT, "lab", "decisions", MECH_ADR + "-*.md")))
    if not hits:
        return None
    return card_add_ts(rel(hits[0]))


def all_cards():
    return sorted(glob.glob(os.path.join(ROOT, "lab", "hypotheses", "H-*.md")))


def card_file(hid):
    """Файл карточки по её id — тем же правилом, что и обход `all_cards()`.

    Форма `{hid}-*.md` требует дефис после номера, а `H-0065.md` его не имеет: поиск
    возвращал пустоту, и сверка снимка с git красила `НЕТ_GIT` по причине «имя файла без
    суффикса». Освобождение по форме имени — тот же класс самоосвобождения, что и по
    отсутствию ключа, поэтому правило поиска одно на весь прибор.
    """
    hits = sorted(glob.glob(os.path.join(ROOT, "lab", "hypotheses", hid + "*.md")))
    return hits[0] if hits else None


def card_git_date(hid):
    """Дата добавления файла карточки по git: (iso|None, unix|None)."""
    path = card_file(hid)
    if path is None:
        return None, None
    ts = card_add_ts(rel(path))
    return (iso(ts) if ts is not None else None), ts


def card_class(path):
    """Класс карточки: рубрика не предъявляема (шапка/ключ) или карточка под правилом."""
    fm, _err = front_matter(path)
    if fm is None:
        return UNPARSED_CLASS
    if "lean" not in fm:
        return NO_LEAN_CLASS
    return None


def read_registry(path):
    """Снимок реестра с диска: {id: (поле2, причина)}; комментарии и пустые строки пропущены."""
    rows = {}
    if not os.path.isfile(path):
        return rows
    for line in io.open(path, encoding="utf-8").read().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        key = parts[0].strip()
        rows[key] = (parts[1].strip() if len(parts) > 1 else "",
                     parts[2].strip() if len(parts) > 2 else "")
    return rows


def exempt_recompute():
    """Множество карточек, которым рубрика не может быть предъявлена, — по дереву, не по списку."""
    out = {}
    for path in all_cards():
        cls = card_class(path)
        if cls is None:
            continue
        m = re.search(r"(H-\d{4})", os.path.basename(path))
        out[m.group(1) if m else os.path.basename(path)] = cls
    return out


def defects_recompute():
    """Число нарушений у каждой карточки под правилом (весь круг, не окно)."""
    counts = {}
    for path in all_cards():
        m = re.search(r"(H-\d{4})", os.path.basename(path))
        if m is None or card_class(path) is not None:
            continue
        rc, text = _gate(ROOT, m.group(1))
        if rc:
            v = re.search(r"нарушений=(\d+)", text)
            counts[m.group(1)] = int(v.group(1)) if v else 1
    return counts


def diff_legacy(rows, recompute, mech, date_of=None):
    """Находки сверки снимка освобождений с пересчётом. Освобождение обязано быть названным.

    `date_of` — функция (id → (iso, unix)), по умолчанию настоящая (дата добавления по git).
    Через неё самопроверка сажает состояния, которых на дереве нет: карточка «добавленная
    после порога» невоспроизводима живым git, а именно она доказывает, что ПОЗДНО исполняется.
    """
    date_of = date_of or card_git_date
    findings = []
    for hid in sorted(recompute):
        if hid not in rows:
            findings.append(f"AUDIT_FINDING\tНЕ_НАЗВАНА\t{hid}\t{recompute[hid]}")
            continue
        date, reason = rows[hid]
        real, ts = date_of(hid)
        if real is None:
            findings.append(f"AUDIT_FINDING\tНЕТ_GIT\t{hid}\tнет даты добавления файла")
        elif date != real:
            findings.append(f"AUDIT_FINDING\tДАТА\t{hid}\tснимок={date} git={real}")
        elif mech is not None and ts >= mech:
            findings.append(f"AUDIT_FINDING\tПОЗДНО\t{hid}\t{date} не раньше порога {iso(mech)}")
        if len(reason) < MIN_REASON:
            findings.append(f"AUDIT_FINDING\tПРИЧИНА\t{hid}\t{len(reason)} знаков")
    for hid in sorted(rows):
        if hid not in recompute:
            findings.append(f"AUDIT_FINDING\tОТЖИЛО\t{hid}\tрубрика уже есть либо карточка исчезла")
    return findings


def diff_defects(rows, recompute, mech=None, date_of=None):
    date_of = date_of or card_git_date
    findings = []
    for hid in sorted(recompute):
        if hid not in rows:
            findings.append(f"AUDIT_FINDING\tНЕ_НАЗВАНА\t{hid}\tнарушений={recompute[hid]}")
            continue
        count, reason = rows[hid]
        if not count.isdigit():
            findings.append(f"AUDIT_FINDING\tСЧЁТ\t{hid}\tполе «{count}» не число")
        elif int(count) != recompute[hid]:
            findings.append(f"AUDIT_FINDING\tСЧЁТ\t{hid}\tбыло={count} стало={recompute[hid]}")
        if len(reason) < MIN_REASON:
            findings.append(f"AUDIT_FINDING\tПРИЧИНА\t{hid}\t{len(reason)} знаков")
        # Свежую карточку нельзя освободить авто-текстом: генератор ставит заготовку, а заготовка
        # краснит. Иначе `defects --write` оставался бы кнопкой «позеленеть» — тем же
        # самоосвобождением, против которого этот круг.
        if mech is not None and reason == AUTO_REASON_FRESH:
            _d, ts = date_of(hid)
            if ts is not None and ts >= mech:
                findings.append(f"AUDIT_FINDING\tАВТОПРИЧИНА\t{hid}\t"
                                f"добавлена {iso(ts)} позже порога {iso(mech)} — причину пишет человек")
    for hid in sorted(rows):
        if hid not in recompute:
            findings.append(f"AUDIT_FINDING\tОТЖИЛО\t{hid}\tкарточка больше не нарушает гейт")
    return findings


def cmd_snapshot(args):
    """Пишет снимок реестра: освобождений (`legacy`) или нарушений (`defects`)."""
    mech = mechanism_ts()
    target = args.write or os.path.join(
        ROOT, LEGACY_LIST if args.cmd == "legacy" else DEFECTS_LIST)
    old_text = io.open(target, encoding="utf-8").read() if os.path.isfile(target) else ""
    old = read_registry(target)
    if args.cmd == "legacy":
        recompute = exempt_recompute()
        lines = [f"# порог механизма {MECH_ADR}: {iso(mech) if mech else 'не найден'}"]
        for hid in sorted(recompute):
            date, ts = card_git_date(hid)
            if date is None:
                # Строка без даты из git не может быть доказательством «историчности», поэтому
                # снимок пишет заведомо красный маркер: сверка на нём покраснит `НЕТ_GIT`,
                # и молчаливого освобождения не получится.
                print(f"snapshot: {hid} нет даты добавления по git", file=sys.stderr)
                date = "нет-даты"
            side = "до" if ts is not None and mech and ts < mech else "после"
            lines.append(f"{hid}\t{date}\tкарточка добавлена {date}, {side} порога {MECH_ADR}; "
                         f"класс освобождения: {recompute[hid]}")
    else:
        recompute = defects_recompute()
        lines = ["# нарушения карточек под правилом; поле 2 — число нарушений, которое видит гейт"]
        todo = 0
        for hid in sorted(recompute):
            _d, ts = card_git_date(hid)
            fresh = mech is not None and ts is not None and ts >= mech
            prev = old.get(hid, ("", ""))[1]
            if prev and prev not in (AUTO_REASON_OLD, AUTO_REASON_FRESH):
                reason = prev          # человеческий текст не затирается пересчётом
            elif fresh:
                reason = AUTO_REASON_FRESH
                todo += 1
            else:
                reason = AUTO_REASON_OLD
            lines.append(f"{hid}\t{recompute[hid]}\t{reason}")
        print(f"строк={len(recompute)} требуют человеческой причины={todo}", file=sys.stderr)
    # Человеческий комментарий в съёмке файла — часть удостоверения, а не мусор: пересчёт
    # обязан обновлять строки, не затирая то, что в файл вписал человек (правило то же, что
    # с причиной освобождения).
    keep = [l for l in old_text.splitlines() if l.startswith("#") and l not in lines]
    lines = lines[:1] + keep + lines[1:]
    text = "\n".join(lines) + "\n"
    if args.write:
        with io.open(args.write, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"записан {args.write} строк={len(recompute)}")
    else:
        print(text, end="")
    return 0


def cmd_audit(args):
    # ADR-0079: порог круга измеряется по дате появления файла, а дату даёт история. В клоне
    # глубиной один коммит все карточки выглядят добавленными сегодня, и аудит печатал бы
    # выдуманные находки: замер пина — 88 строк класса `ДАТА` против нуля на полной истории.
    if historylib.is_shallow(ROOT):
        return historylib.refuse("AUDIT")
    files = all_cards()
    if not getattr(args, "all", False):
        files = files[-args.n:] if args.n else files
    legacy = 0
    unparsed = 0
    # Счётчик находок обязана иметь выходную ветку: до `E-0129` аудит печатал
    # `CYCLE H-xxxx=FAIL нарушений=N` и возвращал ноль всегда, поэтому названный вердикт
    # покраснить шаг не мог — хвост `E-0127`, п. 3 («прибор знает форму, но не знает, есть
    # ли в шаге чем вынести вердикт»).
    bad_cards = 0
    violating = []
    for path in files:
        fm, err = front_matter(path)
        m = re.search(r"(H-\d{4})", os.path.basename(path))
        hid = (fm or {}).get("id") or (m.group(1) if m else path)
        if fm is None:
            unparsed += 1
            print(f"КАРТОЧКА {hid}: шапка не разобрана ({err})")
            continue
        if "lean" not in fm:
            legacy += 1
            print(f"КАРТОЧКА {hid}: {PRE_MECHANISM_NOTE}, prior_art={len(fm.get('prior_art') or [])}")
            continue
        rc = cmd_gate(type("A", (), {"hid": str(hid), "skip_lean": True})())
        print(f"КАРТОЧКА {hid}: под правилом, {'оформлена' if rc == 0 else 'НАРУШЕНИЯ'}")
        bad_cards += 1 if rc else 0
        if rc:
            violating.append(hid)
    print(f"AUDIT карточек={len(files)} исторических={legacy} под_правилом={len(files) - legacy}")
    # Отдельная строка, а не хвост прежней: строка `AUDIT ` заморожена в таблицах ожиданий
    # закрытых циклов, и менять её ради нового счётчика — значит сделать чужой прогон
    # несходным (правило «замороженные пороги не правятся задним числом»).
    print(f"AUDIT_BAD карточек_с_нарушениями={bad_cards}")
    print(f"AUDIT_SHAPKA не_разобранных={unparsed}")
    # Освобождение больше не следует из отсутствия ключа: оно стоит в реестре, а реестр сверяется
    # с пересчётом по дереву и с датой добавления файла по git. Порог кода — НАЗВАННОСТЬ: находки
    # свери обоих реестров плюс карточки под правилом, чьих нарушений нет в снимке. Одно
    # `bad_cards` краснило бы каждый прогон из-за десяти давно известных и названных нарушений
    # и ничего не объяснял, а одно `total` молчал бы, если бы список назвали, но пересчёт
    # перестал его проверять.
    mech = mechanism_ts()
    rows = read_registry(os.path.join(ROOT, LEGACY_LIST))
    findings = diff_legacy(rows, exempt_recompute(), mech)
    print(f"AUDIT_LIST строк={len(rows)} расхождений={len(findings)}")
    drows = read_registry(os.path.join(ROOT, DEFECTS_LIST))
    dfinds = diff_defects(drows, defects_recompute(), mech)
    print(f"AUDIT_DEFECTS строк={len(drows)} расхождений={len(dfinds)}")
    for line in findings + dfinds:
        print(line)
    total = len(findings) + len(dfinds)
    print(f"AUDIT_MECH порог={iso(mech) if mech else 'нет'} находок={total}")
    bad_cards = total + sum(1 for h in violating if h not in drows)
    return 1 if bad_cards else 0


GOOD_CARD = {
    "id": "H-0000", "claim": "посаженный корректный круг", "falsifier": "посаженный фальсификатор",
    "oracle": "лабораторный тест", "date": "2026-10-23", "prior_art": ["L-0000"],
    "lean": {"решение": "не применён",
             "причина": "утверждение говорит о времени и байтах, модель его не задаст",
             "пространство": "нет", "без_времени": "нет",
             "для_всех": "да", "дешевле_стенда": "нет"},
}

# Четыре «да» + «применён»: ветка, в которой гейт обязан потребовать модель и скомпилировать её.
def _lean_applied(модель="lab/lean/VecDHT/Selftest.lean"):
    return {"решение": "применён", "причина": "конечное пространство, ∀-инвариант без времени",
            "модель": модель, "пространство": "да", "без_времени": "да",
            "для_всех": "да", "дешевле_стенда": "да",
            "доказывает": "посадочная теорема о конечном списке, не свойство продукта",
            "соответствие_кода": "не проверено: посадочная модель, прибора уровня 2 нет"}


# Четыре посаженных кейса, обещанных рубрикой (`lab/lean-rubric.md:73`). Каждый обязан покраснеть
# своей причиной, иначе «поля проверяются» — это снова текст, а не прибор.
LEAN_FIELD_CASES = 4


GOOD_MODEL = ("import Std\n\ndef f (n : Nat) : Nat := n + 1\n"
              "def ltB (a b : Nat) : Bool := if a < b then true else false\n\n"
              "theorem up : ((List.range 4).all (fun n => ltB n (f n))) = true := "
              "by native_decide\n")
SORRY_MODEL = ("import Std\n\ntheorem whatever : 1 = 1 := by sorry\n")
BROKEN_MODEL = ("import Std\n\ndef f (n : Nat) : Nat := n +\n")

# Годная карточка эксперимента: без неё позитивный контроль гейта был бы невозможен —
# `check_experiment` требует файл, которого в временном лаборатории до 2026-10-24 не было.
GOOD_EXPERIMENT = {"id": "E-0000", "hypothesis": "H-0000", "status": "running",
                   "base_commit": "c0ffee1 (пре-регистрация: продукт не тронут)",
                   "environment": "лабораторный selftest, один процесс",
                   "command": "python lab/cycle-gate.py selftest",
                   "threshold": "годная карточка проходит, посаженные нарушения отбиты",
                   "verdict": "pending"}


# (название, мутация карточки, подстрока, по которой узнаём нужную причину отказа)
DEFECTS = [
    ("prior_art пуст", dict(prior_art=[]), "не сделан"),
    ("строки нет в индексе", dict(prior_art=["L-0099"]), "в индексе такой строки нет"),
    ("четыре да и отказ от модели", dict(lean={"решение": "не применён",
                                               "причина": "не захотел писать модель, лень",
                                               "пространство": "да", "без_времени": "да",
                                               "для_всех": "да", "дешевле_стенда": "да"}),
     "рубрика дала четыре «да»"),
    ("применён без модели", dict(lean={"решение": "применён", "причина": "х" * 30,
                                       "пространство": "да", "без_времени": "да",
                                       "для_всех": "да", "дешевле_стенда": "да"}),
     "`lean.модель` не названа"),
    ("нет ключа lean", {"__del__": "lean"}, "нет ключа `lean:`"),
    ("только статьи, код не читали", dict(prior_art=["L-0001"]), "ни одной записи класса"),
    # Модель — самая дорогая ветка гейта (она зовёт компилятор), и до 2026-10-23 ни один
    # посаженный дефект её не касался: «все дефекты отбиты» мог обеспечить и гейт, который
    # отвергает всё подряд. Ниже — три дефекта модели плюс позитивный контроль компиляции.
    ("модель названа, но её нет", dict(lean=_lean_applied(модель="lab/lean/VecDHT/Netu.lean")),
     "не найдена на диске"),
    ("модель с sorry", {"lean": _lean_applied(), "__model__": SORRY_MODEL},
     "содержит sorry"),
    ("модель не компилируется", {"lean": _lean_applied(), "__model__": BROKEN_MODEL,
                                 "__compile__": True},
     "не компилируется"),
    # Карточка эксперимента — то, что пре-регистрирует порог. Гейт смотрел только на карточку
    # гипотезы и потому пропустил собственный цикл `E-0092`: пороги, фальсификатор, helper и
    # PRE_FIX были в `H-0092-*.md` (коммит `c41610a`), а `lab/experiments/E-0092-*.md` в том
    # коммите отсутствовал. Ниже — обе ветки этого правила, посаженные как дефекты.
    ("нет карточки эксперимента", {"__exp__": "missing"}, "не найдена — пре-регистрация"),
    ("в карточке E не назван порог",
     {"__exp__": {"threshold": "", "command": ""}}, "в карточке E-0000 не названы"),
    # Посадка на уже случившемся: закрытие `E-0095` оставило `status: pre-registered` при
    # `verdict: "supports"`. Правило без посаженного дефекта — это правило, которое никто не
    # проверял исполнением, поэтому ниже оно заведено и как проверка, и как мутация.
    ("вердикт вынесен, а карточка ещё пре-регистрируется",
     {"__exp__": {"status": "pre-registered", "verdict": "supports"}},
     "не переведена в закрытое состояние"),
    # Рубрика Lean обещала четыре посаженных кейса на поля `доказывает:`/`соответствие_кода:`.
    # Модель в мутациях присутствует (`__model__`), иначе дефект маскировался бы ранней причиной
    # «модель не найдена», и кейс ничего не проверял бы.
    ("применён без `доказывает`",
     {"lean": dict(_lean_applied(), **{"доказывает": ""}), "__model__": GOOD_MODEL},
     "`lean.доказывает` не назван"),
    ("`доказывает` без предмета",
     {"lean": dict(_lean_applied(), **{"доказывает": "доказано"}),
      "__model__": GOOD_MODEL},
     "короче 25 знаков"),
    ("соответствие формулировкой, а не прибором",
     {"lean": dict(_lean_applied(),
                   **{"соответствие_кода": "проверено исполнением, не рассуждением"}),
      "__model__": GOOD_MODEL},
     "не называет прибор путём"),
    ("прибор соответствия не найден",
     {"lean": dict(_lean_applied(),
                   **{"соответствие_кода":
                      "проверено тестом crates/vecdht-wire/tests/netu.rs"}),
      "__model__": GOOD_MODEL},
     "не найден на диске"),
]

# Посадки сверки реестров (`H-0167`). Их нельзя посадить живым деревом: дата добавления
# файла берётся из git, а свежую карточку с датой «после порога» git не воспроизведёт —
# она ещё не в истории. Поэтому функции сверки принимают `date_of`, и самопроверка
# подставляет даты сама. Ожидаемый класс — второе поле строки `AUDIT_FINDING`; пустое
# поле означает «годный снимок обязан молчать» (иначе красным становится всё подряд).
REG_MECH = 1_000_000_000
REG_OLD_TS, REG_NEW_TS = 978_307_200, 1_100_000_000
REG_OLD_D, REG_NEW_D = iso(REG_OLD_TS), iso(REG_NEW_TS)
REG_REASON = "карточка закрыта и оформлена до того, как рубрика потребовала этих полей"
REG_LEGACY = {"H-0001": (REG_OLD_D, REG_REASON)}
REG_LEGACY_RECOUNT = {"H-0001": NO_LEAN_CLASS}
REG_OLD_DATES = {"H-0001": (REG_OLD_D, REG_OLD_TS)}
REG_NEW_DATES = {"H-0001": (REG_NEW_D, REG_NEW_TS)}
REG_DEFECTS = {"H-0001": ("2", REG_REASON)}
REG_DEFECTS_RECOUNT = {"H-0001": 2}

REG_CASES = [
    ("годный снимок освобождений", "legacy", dict(REG_LEGACY), dict(REG_LEGACY_RECOUNT),
     dict(REG_OLD_DATES), ""),
    ("освобождение не названо", "legacy", {}, dict(REG_LEGACY_RECOUNT), dict(REG_OLD_DATES),
     "НЕ_НАЗВАНА"),
    ("дата снимка расходится с git", "legacy",
     {"H-0001": (REG_NEW_D, REG_REASON)}, dict(REG_LEGACY_RECOUNT), dict(REG_OLD_DATES), "ДАТА"),
    ("карточка свежее порога", "legacy", {"H-0001": (REG_NEW_D, REG_REASON)},
     dict(REG_LEGACY_RECOUNT), dict(REG_NEW_DATES), "ПОЗДНО"),
    ("строка снимка отжила", "legacy",
     {"H-0001": (REG_OLD_D, REG_REASON), "H-0002": (REG_OLD_D, REG_REASON)},
     dict(REG_LEGACY_RECOUNT), dict(REG_OLD_DATES), "ОТЖИЛО"),
    ("причина короче порога", "legacy", {"H-0001": (REG_OLD_D, "коротко")},
     dict(REG_LEGACY_RECOUNT), dict(REG_OLD_DATES), "ПРИЧИНА"),
    ("даты по git нет", "legacy", dict(REG_LEGACY), dict(REG_LEGACY_RECOUNT), {}, "НЕТ_GIT"),
    ("годный снимок нарушений", "defects", dict(REG_DEFECTS), dict(REG_DEFECTS_RECOUNT),
     dict(REG_OLD_DATES), ""),
    ("нарушение не названо", "defects", {}, dict(REG_DEFECTS_RECOUNT), dict(REG_OLD_DATES),
     "НЕ_НАЗВАНА"),
    ("число нарушений изменилось", "defects", {"H-0001": ("3", REG_REASON)},
     dict(REG_DEFECTS_RECOUNT), dict(REG_OLD_DATES), "СЧЁТ"),
    ("строка нарушений отжила", "defects",
     {"H-0001": ("2", REG_REASON), "H-0002": ("1", REG_REASON)}, dict(REG_DEFECTS_RECOUNT),
     dict(REG_OLD_DATES), "ОТЖИЛО"),
    ("свежую карточку освобождает авто-текст", "defects",
     {"H-0001": ("2", AUTO_REASON_FRESH)}, dict(REG_DEFECTS_RECOUNT), dict(REG_NEW_DATES),
     "АВТОПРИЧИНА"),
]


def _reg_dates(pairs):
    def f(hid):
        return pairs.get(hid, (None, None))
    return f


def _use_root(root):
    globals()["ROOT"] = root
    globals()["INDEX"] = os.path.join(root, "lab", "library", "index.jsonl")


def _temp_lab():
    """Копия рабочего индекса + синтетическая строка L-0000 с целью H-0000.

    Без живой копии индекса selftest падал бы по причине «индекс не найден» и для годной
    карточки — невыполнимый по построению контроль (ДИАГНОЗ-1 из E-0087 уже про это).
    """
    import os
    root = tempfile.mkdtemp(prefix="cycle-gate-selftest-")
    os.makedirs(os.path.join(root, "lab", "hypotheses"))
    os.makedirs(os.path.join(root, "lab", "experiments"))
    os.makedirs(os.path.join(root, "lab", "library"))
    os.makedirs(os.path.join(root, "lab", "lean", "VecDHT"))
    extra = {"id": "L-0000", "title": "самопроверка гейта", "url": "https://github.com/libp2p/specs",
             "cite": "github:libp2p/specs", "verified": "2026-10-23", "depth": "текст выборочно",
             "kind": "спека", "gives": "годная строка для позитивного контроля",
             "targets": ["H-0000"], "status": "в работе", "action": "", "cost_min": 1,
             "opened": "2026-10-23", "ref": "c750236de43cd8b246a824b377dfdb26bae686db",
             "path": "README.md"}
    with io.open(os.path.join(root, "lab", "library", "index.jsonl"), "w", encoding="utf-8") as fh:
        for r in load_index()[0] + [extra]:
            r.pop("_line", None)
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return root


def _gate(root, hid, skip_lean=True):
    saved = ROOT
    _use_root(root)
    buf = io.StringIO()
    real = sys.stdout
    try:
        sys.stdout = buf
        rc = cmd_gate(type("A", (), {"hid": hid, "skip_lean": skip_lean})())
    finally:
        sys.stdout = real
        _use_root(saved)
    return rc, buf.getvalue()


def cmd_selftest(_args):
    """Гейт обязан отбивать посаженные нарушения и пропускать годную карточку."""
    root = _temp_lab()
    try:
        import yaml
    except Exception:
        print("SELFTEST не выполнен: нет PyYAML")
        return 2
    path = os.path.join(root, "lab", "hypotheses", "H-0000-selftest.md")
    exp_path = os.path.join(root, "lab", "experiments", "E-0000-selftest.md")

    model_file = os.path.join(root, "lab", "lean", "VecDHT", "Selftest.lean")

    def write_exp(fm):
        with io.open(exp_path, "w", encoding="utf-8") as fh:
            fh.write("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) +
                     "\n---\n# посадка\n")

    def write(fm):
        fm = dict(fm)
        drop = fm.pop("__del__", None)
        if drop:
            fm.pop(drop, None)
        body = fm.pop("__model__", None)
        if body is None:
            if os.path.isfile(model_file):
                os.remove(model_file)
        else:
            io.open(model_file, "w", encoding="utf-8").write(body)
        fm.pop("__compile__", None)
        # Карточка эксперимента восстанавливается перед каждой мутацией: иначе «нет карточки»
        # отравил бы все последующие дефекты своей причиной (они бы проходили по чужому нарушению).
        exp = fm.pop("__exp__", None)
        if exp == "missing":
            if os.path.isfile(exp_path):
                os.remove(exp_path)
        else:
            write_exp(dict(GOOD_EXPERIMENT, **(exp or {})))
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) +
                     "\n---\n# посадка\n")

    write_exp(GOOD_EXPERIMENT)
    write(GOOD_CARD)
    good_rc, text = _gate(root, "H-0000")
    print(f"  КОНТРОЛЬ годная карточка: rc={good_rc} "
          f"{'ПРОЙДЕН' if good_rc == 0 else 'СЕЛ — гейт блокирует заведомо годный круг'}")
    if good_rc != 0:
        print("".join("    | " + l + "\n" for l in text.splitlines()))
    ok = 1 if good_rc == 0 else 0
    for name, mutation, reason in DEFECTS:
        mutation = dict(mutation)
        compile_it = bool(mutation.get("__compile__", False))
        write(dict(GOOD_CARD, **mutation))
        rc, text = _gate(root, "H-0000", skip_lean=not compile_it)
        if rc == 0:
            mark = "СЕЛ"
        elif reason in text:
            mark = "ОТБИТ"
        else:
            mark = "ОТБИТ НЕ ПО ТОЙ ПРИЧИНЕ"
        print(f"  ДЕФЕКТ {name}: rc={rc} {mark}")
        if rc == 1 and reason not in text:
            print("    | " + " | ".join(l.strip() for l in text.splitlines()
                                        if "НАРУШЕНИЕ" in l)[:220])
        ok += 1 if (rc == 1 and reason in text) else 0
    # Позитивный контроль дорогой ветки: годная модель при четырёх «да» обязана ПРОЙТИ
    # компиляцию. Без него «все дефекты отбиты» удовлетворяет и гейт, который валит всё подряд.
    write(dict(GOOD_CARD, lean=_lean_applied(), __model__=GOOD_MODEL))
    rc_ok, text_ok = _gate(root, "H-0000", skip_lean=False)
    print(f"  КОНТРОЛЬ годная модель при четырёх «да»: rc={rc_ok} "
          f"{'ПРОЙДЕН' if rc_ok == 0 else 'СЕЛ — гейт валит заведомо годный круг'}")
    if rc_ok != 0:
        print("    | " + " | ".join(l.strip() for l in text_ok.splitlines())[:240])
    ok += 1 if rc_ok == 0 else 0
    # Сверка реестров — отдельные посадки: они судят не карточку, а список, и живым деревом
    # невоспроизводимы (дата «после порога» у карточки, которой ещё нет в истории).
    reg_ok = 0
    for name, kind, rows, recount, dates, expect in REG_CASES:
        date_of = _reg_dates(dates)
        fnd = (diff_legacy(rows, recount, REG_MECH, date_of) if kind == "legacy"
               else diff_defects(rows, recount, REG_MECH, date_of))
        hit = any(l.split("\t")[1] == expect for l in fnd) if expect else not fnd
        mark = ("ПРОЙДЕН" if expect == "" else "ОТБИТ") if hit else "СЕЛ"
        print(f"  РЕЕСТР {name}: находок={len(fnd)} {mark}")
        if not hit:
            print("    | " + " | ".join(l[:80] for l in fnd)[:200])
        reg_ok += 1 if hit else 0
    ok += reg_ok
    shutil.rmtree(root, ignore_errors=True)
    total = len(DEFECTS) + 2 + len(REG_CASES)
    print(f"SELFTEST годный_круг={'пропущен' if good_rc == 0 else 'заблокирован'} "
          f"отбито={ok} из {total}")
    print(f"CYCLEGATE_SELFTEST total={total} passed={ok} good_card_rc={good_rc}")
    print(f"CYCLEGATE_LEAN_FIELD_CASES={LEAN_FIELD_CASES}")
    print(f"CYCLEGATE_REGISTRY_CASES={len(REG_CASES)} отбито={reg_ok}")
    return 0 if ok == total else 1


def main():
    # `cycle-gate.py H-0092` без подкоманды: агент, который впервые открыл репозиторий, обязан
    # угадать команду с первой попытки; argparse иначе съедает позиционный аргумент как выбор.
    if len(sys.argv) > 1 and re.match(r"^H-\d{4}$", sys.argv[1]):
        sys.argv.insert(1, "gate")
    # `--audit` вместо `audit`: докстринг долго обещал именно такую форму, и агент, который
    # читал только её, получал «invalid choice» — переводим ошибку в работу, а не в отказ.
    if len(sys.argv) > 1 and sys.argv[1] in ("--audit", "-a"):
        sys.argv[1] = "audit"
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    g = sub.add_parser("gate", help="проверить карточку H-XXXX")
    g.add_argument("hid")
    g.add_argument("--skip-lean", action="store_true")
    a = sub.add_parser("audit", help="отчёт по последним N карточкам либо по всему кругу")
    a.add_argument("-n", type=int, default=8)
    a.add_argument("--all", action="store_true",
                   help="весь круг вместо окна: дефект не обязан «выпадать» из последних пяти")
    for name in ("legacy", "defects"):
        sn = sub.add_parser(name, help=f"пересчёт снимка `{name}` по дереву")
        sn.add_argument("--write", help="куда записать снимок (по умолчанию — stdout)")
    s = sub.add_parser("selftest", help="посаженные нарушения обязаны отбиваться")
    # обратная совместимость: `cycle-gate.py H-0092` без подкоманды
    args, extra = p.parse_known_args()
    if args.cmd == "gate":
        return cmd_gate(args)
    if args.cmd == "audit":
        return cmd_audit(args)
    if args.cmd in ("legacy", "defects"):
        return cmd_snapshot(args)
    if args.cmd == "selftest":
        return cmd_selftest(args)
    if extra and re.match(r"^H-\d{4}$", extra[0]):
        return cmd_gate(type("A", (), {"hid": extra[0], "skip_lean": "--skip-lean" in extra})())
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
