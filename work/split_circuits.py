from pathlib import Path

# Разделение гейтов на два контура (из ресёрча: seL4/Rust разделяют «корректность механизма»
# и «целостность репозитория»). Сейчас они в одном списке: ошибка в README блокирует
# оценку механизма, и наоборот — зелёный README выглядит как подтверждение безопасности.
#
# Контур A (механизм): политика, посредник, журнал, опора, модели.
# Контур B (целостность): ссылки, печати, README, формулировки, структура.
#
# Вердикты независимы: --circuit a / b / all.
p = Path("bin/hs.py")
t = p.read_text(encoding="utf-8")

old = '''    checks = [("секреты", gate_secrets), ("утверждения", gate_claims),
              ("ссылки", gate_links), ("критерии", gate_criteria), ("аудит", gate_audit), ("отказы", gate_failures), ("процедуры", gate_procs), ("формулировки", gate_wording), ("README", gate_readme_numbers), ("модели", gate_models), ("утверждения-проверка", gate_claims_run), ("самоссылка", gate_selfref), ("харнессы", gate_harnesses), ("глубины", gate_depths), ("автономия", gate_autonomy), ("решения", gate_adoptions), ("ядро утверждений", gate_core_claims), ("способности", gate_capabilities), ("журналы", gate_journals), ("рецензии", gate_reviews), ("пре-регистрация", gate_prereg), ("лаборатория", gate_lab), ("печати", gate_seals), ("отсутствие", gate_absence), ("компиляция", gate_compile), ("векторы", gate_vectors), ("покрытие", gate_coverage), ("большие файлы", gate_bigfiles), ("индекс прогонов", gate_runs_index)]'''

new = '''    # Два независимых контура (ресёрч: seL4 и Rust разделяют корректность механизма и
    # целостность репозитория). Ошибка в README не должна выглядеть как провал механизма,
    # а зелёный README — как подтверждение безопасности.
    #
    # Контур A — механизм: политика, посредник, журнал, опора, модели, компиляция.
    # Контур B — целостность: ссылки, печати, README, формулировки, структура, индексы.
    circuit_a = [("секреты", gate_secrets), ("критерии", gate_criteria), ("отказы", gate_failures),
                 ("модели", gate_models), ("утверждения-проверка", gate_claims_run),
                 ("самоссылка", gate_selfref), ("журналы", gate_journals),
                 ("автономия", gate_autonomy), ("способности", gate_capabilities),
                 ("компиляция", gate_compile), ("векторы", gate_vectors)]
    circuit_b = [("утверждения", gate_claims), ("ссылки", gate_links), ("аудит", gate_audit),
                 ("процедуры", gate_procs), ("формулировки", gate_wording),
                 ("README", gate_readme_numbers), ("харнессы", gate_harnesses),
                 ("глубины", gate_depths), ("решения", gate_adoptions),
                 ("ядро утверждений", gate_core_claims), ("рецензии", gate_reviews),
                 ("пре-регистрация", gate_prereg), ("лаборатория", gate_lab),
                 ("печати", gate_seals), ("отсутствие", gate_absence),
                 ("покрытие", gate_coverage), ("большие файлы", gate_bigfiles),
                 ("индекс прогонов", gate_runs_index)]
    which = getattr(args, "circuit", "all")
    if which == "a":
        checks = circuit_a
    elif which == "b":
        checks = circuit_b
    else:
        checks = circuit_a + circuit_b'''

assert old in t, "список гейтов не найден"
t = t.replace(old, new, 1)

# Добавляем флаг --circuit в парсер gates.
old_parser = '''def cmd_gates(args) -> int:'''
new_parser = '''def cmd_gates(args) -> int:
    """Все гейты. --circuit a — только механизм, b — только целостность репозитория."""'''
assert old_parser in t
t = t.replace(old_parser, new_parser, 1)

p.write_text(t, encoding="utf-8")
print("гейты разделены на два контура: --circuit a|b|all")
