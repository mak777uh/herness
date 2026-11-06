"""gate_probe — доказать, что гейт умеет падать.

Гейт, который не падает на реалистичном дефекте, ничего не проверяет. Здесь для каждого гейта
подкладывается **похожий на настоящее** дефект во временную копию репозитория, и требуется, чтобы
гейт его заметил. Пустой файл дефектом не считается: он ловится любым условием.

    python bin/gate_probe.py              # все пробы
    python bin/gate_probe.py --only секреты ссылки
    python bin/gate_probe.py --list
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bin.hs as hs  # noqa: E402

# Что копируется в песочницу: ровно то, что читают пробы. Копия полного репозитория слишком дорога.
COPY = [
    "CLAIMS.md",
    "NOT-CLAIMED.md",
    "README.md",
    "depths.json",
    "harnesses.json",
    "docs",
    "lab",
    "accept",
    "src",
    "core",
    "bin",
    "procedures.json",
    "capabilities.json",
    "tests",
    "research",
    "profiles.json",
    "evidence",
    "inbox",
    "runs",
]


def sandbox() -> Path:
    target = Path(tempfile.mkdtemp(prefix="gate-probe-"))
    for name in COPY:
        source = ROOT / name
        if not source.exists():
            continue
        destination = target / name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns("*.bin", "__pycache__"))
        else:
            shutil.copy2(source, destination)
    return target


def probe_secrets(root: Path) -> None:
    # Ключ собирается из частей: иначе сам файл пробы становится находкой гейта секретов.
    key = "-".join(["sk", "proj", "0123456789abcdefghijklmnopqrstuv"])
    (root / "docs" / "PROBE-secret.md").write_text(
        f"# проба\n\nключ провайдера: {key}\n", encoding="utf-8"
    )


def probe_claims(root: Path) -> None:
    path = root / "CLAIMS.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.rstrip("\n") + "\n| C-9999 | утверждение без типа | | `true` | CLAIMS.md | 01.01.2026 | `x` |\n",
        encoding="utf-8",
    )


def probe_claims_columns(root: Path) -> None:
    # Строка короче заголовка: седьмая колонка «ожидание» потеряна при копипасте (F-0053).
    path = root / "CLAIMS.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.rstrip("\n") + "\n| C-9994 | проба без ожидания | test | `true` | CLAIMS.md | 06.11.2026 |\n",
        encoding="utf-8",
    )


def probe_links(root: Path) -> None:
    (root / "docs" / "PROBE-link.md").write_text(
        "# проба\n\nсм. [нет такого файла](PROBE-missing.md)\n", encoding="utf-8"
    )


def probe_depths(root: Path) -> None:
    (root / "docs" / "ADR-9999-probe.md").write_text(
        "# ADR-9999 — проба\n\nДата: 01.01.2026. Статус: предложено.\n", encoding="utf-8"
    )


def probe_harnesses(root: Path) -> None:
    path = root / "harnesses.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("items", []).append({"id": "probe", "name": "проба"})
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def probe_criteria(root: Path) -> None:
    path = root / "docs" / "CRITERIA.md"
    text = path.read_text(encoding="utf-8")
    # Критерий без способа установления и с выдуманным статусом: так выглядит копипаста строки.
    path.write_text(
        text.rstrip("\n") + "\n| K999 | проба | выдуман | | docs/CRITERIA.md |\n", encoding="utf-8"
    )


def probe_failures(root: Path) -> None:
    (root / "lab" / "failures" / "F-9999.md").write_text(
        "id: F-9999\ndate: 06.11.2026\ntitle: проба без обязательных полей\n", encoding="utf-8"
    )


def probe_prereg(root: Path) -> None:
    # Берём существующую пре-регистрацию и закрываем её без вывода: так выглядит «закрыли, потому
    # что надоело». Новая запись без полей тоже дефект, но у неё другая причина (F-0052).
    items = sorted((root / "lab" / "prereg").glob("*.json"))
    if not items:
        raise RuntimeError("нет пре-регистраций для пробы")
    # Берём ЗАКРЫТУЮ запись с выводом: только у неё есть что убрать. У незакрытой удаление
    # conclusion ничего не меняет, и проба молча проходит (F-0052).
    target = None
    for item in items:
        data = json.loads(item.read_text(encoding="utf-8"))
        if data.get("closed") and data.get("conclusion"):
            target = (item, data)
            break
    if target is None:
        raise RuntimeError("нет закрытой пре-регистрации с выводом")
    item, data = target
    data.pop("conclusion", None)
    item.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def probe_adoptions(root: Path) -> None:
    path = root / "lab" / "adoptions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # Внедрённое решение без источника и без отрицательного контроля — так выглядит «взял, потому что
    # понравилось».
    data.append({"id": "A-9999", "mechanism": "проба", "status": "adopted", "decision": "взято"})
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def probe_procs(root: Path) -> None:
    path = root / "procedures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("procedures", []).append({"id": "P-9999", "name": "проба"})
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def first_prereg(root: Path) -> Path | None:
    items = sorted((root / "lab" / "prereg").glob("*.json"))
    return items[0] if items else None


def probe_seals(root: Path) -> None:
    # Печать перестаёт сходиться: файл изменили после запечатывания. Так выглядит правка
    # пре-регистрации задним числом. Проверка ищет sidecar рядом с файлом.
    # Изменение должно попасть В ПРЕФИКС до маркера «## Seal»: хвост после маркера не защищён.
    # Дописать пробел в конец — значит ничего не изменить (так и вышло в первом заходе).
    for store in sorted(root.rglob("*.sha256")):
        target = Path(str(store)[: -len(".sha256")])
        if not target.exists():
            continue
        content = target.read_text(encoding="utf-8")
        marker = content.find("## Seal")
        head = content[:marker] if marker >= 0 else content
        tail = content[marker:] if marker >= 0 else ""
        target.write_text("# правка после запечатывания\n" + head + tail, encoding="utf-8")
        return
    raise RuntimeError("нет запечатанных файлов для пробы")


def probe_vectors(root: Path) -> None:
    path = root / "tests" / "vectors" / "journal.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    chain = data.get("chain") or []
    if not chain:
        raise RuntimeError("нет цепочки векторов")
    chain[0]["event"]["kind"] = "подмена"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def probe_coverage(root: Path) -> None:
    # Артефакт покрытия отстал от реестра: утверждение добавили, пересчёт не сделали.
    path = root / "research" / "claims-coverage.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "total" in data:
        data["total"] = int(data["total"]) + 1
    elif isinstance(data, dict) and "claims" in data:
        data["claims"] = int(data["claims"]) + 1
    else:
        data["probe"] = True
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def probe_core_claims(root: Path) -> None:
    path = root / "lab" / "core-claims.txt"
    if not path.exists():
        raise RuntimeError("нет lab/core-claims.txt")
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\nC-9999\n", encoding="utf-8")


def probe_autonomy(root: Path) -> None:
    # Из правил изъято обязательное поле: так выглядит правка правил «на ходу».
    path = root / "lab" / "autonomy-rules.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("protected_paths", None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def probe_absence(root: Path) -> None:
    path = root / "CLAIMS.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.rstrip("\n") + "\n| C-9998 | отсутствие без артефакта попыток | absence | `true` | "
        "research/outputs/нет-такого.txt | 06.11.2026 | `x` |\n",
        encoding="utf-8",
    )


def probe_wording(root: Path) -> None:
    # Слово силы при слабом типе свидетельства: «доказано» у наблюдения.
    path = root / "CLAIMS.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.rstrip("\n") + "\n| C-9997 | это доказано на практике | observation | `true` | "
        "CLAIMS.md | 06.11.2026 | `x` |\n",
        encoding="utf-8",
    )


def probe_readme_numbers(root: Path) -> None:
    # Число в README, которого нет ни в одном утверждении: документ сильнее дерева.
    path = root / "README.md"
    # Число берём четырёхзначное: регулярка гейта ловит только 1–4 цифры, а пятизначное
    # проходило мимо неё, и проба ничего не доказывала (F-0050).
    path.write_text(
        path.read_text(encoding="utf-8").rstrip("\n") + "\n\nПроба: 7777 прогонов.\n", encoding="utf-8"
    )


def probe_models(root: Path) -> None:
    path = root / "profiles.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault("default", {})["model"] = "какая-то-другая-модель"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def probe_selfref(root: Path) -> None:
    # Новое самоссылочное утверждение: доказательство лежит в research/*.md.
    path = root / "CLAIMS.md"
    text = path.read_text(encoding="utf-8")
    # Самоссылка по определению гейта: команда содержит check_artifacts, а свидетельство — .md в
    # research/. Строка обязана иметь ровно семь полей, иначе гейт её просто пропускает (F-0050).
    path.write_text(
        text.rstrip("\n")
        + "\n| C-9996 | проба самоссылки | test | `python bin/check_artifacts.py C-9996` | "
        "research/INSIGHTS.md | 06.11.2026 | `x` |\n",
        encoding="utf-8",
    )


def probe_selfref_count(root: Path) -> int:
    """Самоссылка может уже быть в базе: считаем рост, а не факт находки."""
    return 1


def probe_compile(root: Path) -> None:
    # Синтаксическая ошибка в скрипте: так выглядит правка, сделанная «на глаз».
    (root / "bin" / "PROBE-broken.py").write_text("def f(:\n    return 1\n", encoding="utf-8")


def probe_lab(root: Path) -> None:
    # Реестр программы без следующей гипотезы: непонятно, что делать дальше.
    path = root / "lab" / "registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("program", {})["next_hypotheses"] = []
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def lab_reads_real_root() -> bool:
    """Валидатор лаборатории читает ROOT модуля, а не песочницу: проба вне изоляции бесполезна."""
    try:
        sys.path.insert(0, str(ROOT))
        from bin import lab as lab_module

        return Path(lab_module.ROOT).resolve() == ROOT.resolve()
    except Exception:  # noqa: BLE001
        return False


def probe_capabilities(root: Path) -> None:
    path = root / "capabilities.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    tools = data.get("tools")
    if isinstance(tools, list) and tools:
        tools.append("probe-fake-tool")
    else:
        data["tools"] = ["probe-fake-tool"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def probe_bigfiles(root: Path) -> None:
    # Файл больше мегабайта в индексе git: данные попали в репозиторий (F-0023).
    import subprocess

    target = root / "PROBE-big.bin"
    target.write_bytes(b"0" * (1024 * 1024 + 1024))
    subprocess.run(["git", "init", "-q"], cwd=str(root), capture_output=True)
    subprocess.run(["git", "add", "-f", "PROBE-big.bin"], cwd=str(root), capture_output=True)


def probe_audit(root: Path) -> None:
    # Инсайт без applies_to: его нельзя перенести, потому что неизвестно куда.
    # Заголовок заметки — строки «ключ: значение» подряд; тело начинается с первой строки без
    # такого вида. Поле insight относится к телу, а не к шапке (иначе заметка молча не разберётся).
    (root / "inbox" / "harness" / "PROBE-insight.md").write_text(
        "from: probe\nto: harness\nkind: insight\nseverity: high\n"
        "repro: python bin/gate_probe.py --only аудит\n\n"
        "insight: проба без адреса\n",
        encoding="utf-8",
    )


def probe_reviews(root: Path) -> None:
    # Рецензия с вердиктом вне словаря: так выглядит копипаста чужой формы.
    (root / "lab" / "reviews" / "PROBE-review.md").write_text(
        "id: R-9999\ndate: 06.11.2026\nclaim: проба\nverdict: принято-наверное\n"
        "artifact_checked: research/outputs/gate-probes.txt\nmethod: проба\n"
        "what_would_kill_it: ничего\n",
        encoding="utf-8",
    )


def probe_claims_run(root: Path) -> None:
    # Утверждение, чья проверка заведомо провалится: команда вернёт ошибку.
    path = root / "CLAIMS.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.rstrip("\n")
        + "\n| C-9995 | проба проверки утверждений | test | `python -c \"raise SystemExit(1)\"` | "
        "research/outputs/gate-probes.txt | 06.11.2026 | `x` |\n",
        encoding="utf-8",
    )


def probe_journals(root: Path) -> None:
    # Порча цепочки: в журнал вставлена строка, не являющаяся JSON. Так выглядит подмена
    # свидетельства после прогона.
    import json as _json

    runs = root / "runs"
    # Гейт берёт последние 60 каталогов по времени изменения, поэтому портить надо именно
    # свежий журнал: испорченный старый в окно проверки не попадёт (так и вышло в первом заходе).
    candidates = [
        path for path in runs.glob("*")
        if path.is_dir() and (path / "events.jsonl").exists() and not path.name.startswith("test-")
    ]
    if not candidates:
        raise RuntimeError("нет журналов с events.jsonl для пробы")
    candidates.sort(key=lambda path: (path / "events.jsonl").stat().st_mtime)
    target = candidates[-1] / "events.jsonl"
    lines = target.read_text(encoding="utf-8").splitlines()
    if len(lines) < 2:
        raise RuntimeError("журнал слишком короткий для пробы")
    lines.insert(1, "{это не json}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def probe_runs_index(root: Path) -> None:
    # Журнал без записи в индексе: так выглядит новый прогон, о котором метрики не знают (F-0054).
    import shutil as _shutil

    source = next(iter(sorted((root / "runs" / "accept").glob("*"))), None)
    if source is None:
        raise RuntimeError("нет журналов для пробы")
    _shutil.copy2(source, root / "runs" / "accept" / "PROBE-unindexed.bin")


PROBES = {
    "секреты": (hs.gate_secrets, probe_secrets),
    "утверждения": (hs.gate_claims, probe_claims),
    "утверждения-колонки": (hs.gate_claims, probe_claims_columns),
    "ссылки": (hs.gate_links, probe_links),
    "глубины": (hs.gate_depths, probe_depths),
    "харнессы": (hs.gate_harnesses, probe_harnesses),
    "критерии": (hs.gate_criteria, probe_criteria),
    "отказы": (hs.gate_failures, probe_failures),
    "пре-регистрация": (hs.gate_prereg, probe_prereg),
    "решения": (hs.gate_adoptions, probe_adoptions),
    "процедуры": (hs.gate_procs, probe_procs),
    "печати": (hs.gate_seals, probe_seals),
    "векторы": (hs.gate_vectors, probe_vectors),
    "покрытие": (hs.gate_coverage, probe_coverage),
    "ядро утверждений": (hs.gate_core_claims, probe_core_claims),
    "автономия": (hs.gate_autonomy, probe_autonomy),
    "отсутствие": (hs.gate_absence, probe_absence),
    "формулировки": (hs.gate_wording, probe_wording),
    "README": (hs.gate_readme_numbers, probe_readme_numbers),
    "модели": (hs.gate_models, probe_models),
    "самоссылка": (hs.gate_selfref, probe_selfref),
    "компиляция": (hs.gate_compile, probe_compile),
    "лаборатория": (hs.gate_lab, probe_lab),
    "способности": (hs.gate_capabilities, probe_capabilities),
    "большие файлы": (hs.gate_bigfiles, probe_bigfiles),
    "аудит": (hs.gate_audit, probe_audit),
    "рецензии": (hs.gate_reviews, probe_reviews),
    "утверждения-проверка": (hs.gate_claims_run, probe_claims_run),
    "журналы": (hs.gate_journals, probe_journals),
    "индекс прогонов": (hs.gate_runs_index, probe_runs_index),
}


# Гейты, читающие файл по пути модуля, а не по переданному root: проба для них делается на
# настоящем файле и сразу откатывается.
IN_PLACE = {
    "лаборатория": "lab/registry.json",
    "пре-регистрация": "lab/prereg",
}


# Быстрые пробы: без внешних процессов и без обхода сотен каталогов. Их можно гонять при каждом
# запуске гейтов, чтобы заметить, когда гейт перестал ловить.
FAST = [
    "секреты",
    "утверждения",
    "утверждения-колонки",
    "ссылки",
    "глубины",
    "харнессы",
    "критерии",
    "отказы",
    "пре-регистрация",
    "процедуры",
    "формулировки",
    "README",
    "самоссылка",
    "компиляция",
    "лаборатория",
]


def run(names: list[str]) -> int:
    rows = []
    broken = 0
    for name, (gate, inject) in PROBES.items():
        if names and name not in names:
            continue
        # Гейты, читающие ROOT модуля (лаборатория), в песочнице не проверяются: подкладываем
        # дефект в настоящий файл и возвращаем его на место сразу после проверки.
        in_place = name in IN_PLACE
        clean = ROOT if in_place else sandbox()
        backup = None
        try:
            if in_place:
                # Резервная копия — каталог целиком (пре-регистрации) или один файл (реестр).
                source = clean / IN_PLACE[name]
                if source.is_dir():
                    backup = {item.name: item.read_text(encoding="utf-8") for item in source.glob("*.json")}
                else:
                    backup = source.read_text(encoding="utf-8")
            baseline = gate(clean)
            inject(clean)
            after = gate(clean)
            fresh = [item for item in after if item not in baseline]
            caught = bool(fresh)
            rows.append((name, len(baseline), len(after), caught))
            if not caught:
                broken += 1
        finally:
            if in_place and backup is not None:
                source = clean / IN_PLACE[name]
                if isinstance(backup, dict):
                    for name_file, content in backup.items():
                        (source / name_file).write_text(content, encoding="utf-8")
                else:
                    source.write_text(backup, encoding="utf-8")
            if not in_place:
                shutil.rmtree(clean, ignore_errors=True)

    lines = ["# Пробы гейтов: падает ли гейт на реалистичном дефекте", ""]
    lines.append(f"{'гейт':16} до  после  поймал")
    for name, before, after, caught in rows:
        lines.append(f"{name:16} {before:>2}  {after:>5}  {'да' if caught else 'НЕТ'}")
    lines += ["", f"поймали: {len(rows) - broken} из {len(rows)}"]
    text = "\n".join(lines) + "\n"
    # Быстрый набор не должен затирать отчёт о полном: у них разные файлы.
    name = "gate-probes-fast.txt" if set(names) == set(FAST) else "gate-probes.txt"
    (ROOT / "research" / "outputs" / name).write_text(text, encoding="utf-8")
    print(text)
    return 0 if broken == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="пробы гейтов")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.list:
        print(", ".join(PROBES))
        return 0
    return run(args.only)


if __name__ == "__main__":
    sys.exit(main())
