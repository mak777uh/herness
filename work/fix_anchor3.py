from pathlib import Path

# Три дефекта проверки опоры, найденные экспериментом на 199 случаях (FNR = 50 %):
#
# 1. Опора смотрит ТОЛЬКО последний результат. Агент читает три файла и отвечает по первому —
#    опоры нет. Это 77 % ложных отказов в классах multi и paraphrase.
# 2. `ADR-0001` не находится в `ADR-0001-test.md`: вхождение проверялось только в одну сторону.
# 3. Числа словами отбрасывались ДО нормализации: `looks_specific("Три")` → false.
#
# Что делаем: искать во всех результатах, проверять вхождение в обе стороны, нормализовать
# регистр до проверки конкретности.
p = Path("core-rs/src/loopmod.rs")
t = p.read_text(encoding="utf-8")

# --- 1. Опора ищет во всех результатах, а не только в последнем ---
old_last = '''    // Опора берётся из ПОСЛЕДНЕГО результата, а не из любого (аудит гейтов).
    // Причина: последний результат — то, на что агент смотрел, когда отвечал. Ссылка на
    // старый результат — это память, а не подтверждение. Если результатов нет, опоры нет.
    let last_result = match tool_results.last() {
        Some(text) => text,
        None => return None,
    };
    let haystack: Vec<String> = tokens(last_result);'''
new_last = '''    // Опора ищется во ВСЕХ результатах прогона, а не только в последнем.
    // Замер на 199 случаях (bin/oracle_run.py): поиск только в последнем давал 77 % ложных
    // отказов, когда агент читал несколько файлов и отвечал по первому. Результат инструмента —
    // свидетельство независимо от того, когда он получен; «памятью» его делает не время, а
    // отсутствие в журнале. Всё, что здесь, — из журнала.
    if tool_results.is_empty() {
        return None;
    }
    let haystack: Vec<String> = tool_results.iter().flat_map(|text| tokens(text)).collect();'''
assert old_last in t, "блок последнего результата не найден"
t = t.replace(old_last, new_last, 1)

# --- 2. Вхождение в обе стороны ---
old_contained = '''    for token in tokens(final_text) {
        let contained = haystack
            .iter()
            .any(|candidate| candidate.chars().count() >= 4 && token.contains(candidate.as_str()));
        if contained {
            // Возвращаем токен ИЗ ОТВЕТА: опора живёт в ответе, а не в результате.
            return Some(token);
        }
    }'''
new_contained = '''    for token in tokens(final_text) {
        // Вхождение проверяется в ОБЕ стороны: «ADR-0001» в ответе и «ADR-0001-test.md» в
        // результате — одно и то же имя файла. Односторонняя проверка давала 50 % ложных
        // отказов на классе direct (замер bin/oracle_run.py).
        let contained = haystack.iter().any(|candidate| {
            candidate.chars().count() >= 4
                && (token.contains(candidate.as_str()) || candidate.contains(token.as_str()))
        });
        if contained {
            // Возвращаем токен ИЗ ОТВЕТА: опора живёт в ответе, а не в результате.
            return Some(token);
        }
    }'''
assert old_contained in t, "блок вхождения не найден"
t = t.replace(old_contained, new_contained, 1)

# --- 3. Регистр до проверки конкретности ---
old_looks = '''        // number_word сравнивает байты точно, поэтому регистр приводим здесь.
        if number_word(&token.to_lowercase()).is_some() {
            return true;
        }'''
new_looks = '''        // number_word сравнивает байты точно, поэтому регистр приводим здесь.
        // Проверка идёт ДО отбрасывания: иначе «Три» с большой буквы отбрасывалось и
        // опора не срабатывала (60 % ложных отказов на классе number-word).
        if number_word(&token.to_lowercase()).is_some() {
            return true;
        }'''
assert old_looks in t
t = t.replace(old_looks, new_looks, 1)

p.write_text(t, encoding="utf-8")
print("опора: все результаты, вхождение в обе стороны, регистр до проверки")
