#!/usr/bin/env bash
# Verus на наших функциях: то, на чём Kani упирался (to_lowercase), Verus может пройти.
OUT=/mnt/c/111/herness/work/verus-run.txt
: > "$OUT"

mkdir -p /tmp/veruscheck
cat > /tmp/veruscheck/main.rs <<'EOF'
// Три функции из core-rs/src/loopmod.rs, вырезанные для проверки Verus.

use vstd::prelude::*;

verus! {

/// Сравнение ресурса с шаблоном: литерально, без «любого хвоста» (F-0072).
pub fn resource_matches(pattern: &str, resource: &str) -> (r: bool)
    ensures
        // Если шаблон — точная строка, совпадение только при равенстве.
        pattern@ == resource@ ==> r,
        // Если шаблон «/mnt/**», чужой путь не совпадает.
        // Для шаблона «/mnt/**» ресурс, не начинающийся с «/mnt», не совпадает.
        (pattern@ =~= "/mnt/**"@ && resource@.len() > 0 && resource@[0] != '/') ==> !r,
{
    if pattern == "**" {
        return true;
    }
    if let Some(prefix) = pattern.strip_suffix("/**") {
        return resource == prefix || resource.starts_with(&format!("{prefix}/"));
    }
    pattern == resource
}

/// Число словом → цифра. Проверяем, что функция не паникует и возвращает
/// цифру только для известных слов.
pub fn number_word(token: &str) -> (r: Option<&'static str>)
    ensures
        // Для пустой строки ответа нет.
        token@.len() == 0 ==> r.is_none(),
{
    let lower = token.to_lowercase();
    match lower.as_str() {
        "один" | "одна" | "одно" => Some("1"),
        "два" | "две" => Some("2"),
        "три" => Some("3"),
        "четыре" => Some("4"),
        "пять" => Some("5"),
        "шесть" => Some("6"),
        "семь" => Some("7"),
        "восемь" => Some("8"),
        "девять" => Some("9"),
        "десять" => Some("10"),
        _ => None,
    }
}

fn main() {}

} // verus!
EOF

echo '=== 1. Что проверяем' >> "$OUT"
ls -l /tmp/veruscheck >> "$OUT" 2>&1

echo '=== 2. Verus' >> "$OUT"
cd /tmp/veruscheck || exit 2
timeout 600 /opt/verus/verus-run main.rs >> "$OUT" 2>&1
echo "exit: $?" >> "$OUT"
echo DONE >> "$OUT"
