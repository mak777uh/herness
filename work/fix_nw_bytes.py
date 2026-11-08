from pathlib import Path

# Ошибка: в таблице number_word длины указаны в СИМВОЛАХ, а сравнение идёт в БАЙТАХ.
# Для кириллицы 1 символ = 2 байта: «три» — 3 символа, но 6 байт. Проверка `len != word_len`
# отбрасывала всё, и number_word всегда возвращала None.
#
# Правильно: брать длину из самого слова (`word.len()` всегда в байтах). Тогда ошибки быть
# не может — и для кириллицы, и для латиницы.
p = Path("core-rs/src/loopmod.rs")
t = p.read_text(encoding="utf-8")

old_start = t.find("fn number_word(token: &str) -> Option<&'static str> {")
old_end = t.find("\n}\n", old_start) + 3
assert old_start > 0 and old_end > old_start, "number_word не найдена"

new_fn = '''fn number_word(token: &str) -> Option<&'static str> {
    // Таблица: слово в нижнем регистре и цифра. Длина НЕ хранится: `word.len()` всегда
    // в байтах, и это единственная мера, по которой идёт сравнение. Хранимая длина в
    // символах давала None для всей кириллицы («три» — 3 символа, но 6 байт).
    const TABLE: &[(&str, &str)] = &[
        ("один", "1"), ("одна", "1"), ("одно", "1"),
        ("два", "2"), ("две", "2"),
        ("три", "3"),
        ("четыре", "4"),
        ("пять", "5"),
        ("шесть", "6"),
        ("семь", "7"),
        ("восемь", "8"),
        ("девять", "9"),
        ("десять", "10"),
        ("одиннадцать", "11"),
        ("двенадцать", "12"),
        ("тринадцать", "13"),
        ("четырнадцать", "14"),
        ("пятнадцать", "15"),
        ("двадцать", "20"),
        ("тридцать", "30"),
        ("сорок", "40"),
        ("пятьдесят", "50"),
        ("сто", "100"),
    ];
    let bytes = token.as_bytes();
    for (word, digit) in TABLE {
        let word_bytes = word.as_bytes();
        // Длина берётся из слова: она всегда в байтах, как и bytes.len().
        if bytes.len() != word_bytes.len() {
            continue;
        }
        // Сравнение точное, байт за байтом: to_ascii_lowercase не поддержан Verus,
        // а регистр уже приведён вызывающим кодом (normalize_token).
        if word_bytes.iter().zip(bytes.iter()).all(|(a, b)| a == b) {
            return Some(digit);
        }
    }
    None
}
'''

t = t[:old_start] + new_fn + t[old_end:]
p.write_text(t, encoding="utf-8")
print("number_word: длина берётся из слова, а не хранится")
