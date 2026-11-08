#!/usr/bin/env bash
# Verus на переписанной number_word: сравнение по длине и байтам, без match по строкам.
OUT=/mnt/c/111/herness/work/verus-nw.txt
: > "$OUT"

mkdir -p /tmp/verusnw
cat > /tmp/verusnw/main.rs <<'EOF'
use vstd::prelude::*;

verus! {

/// Число словом → цифра. Сравнение по длине и байтам.
/// Утверждение: для пустой строки ответа нет.
pub fn number_word(token: &str) -> (r: Option<&'static str>)
    ensures
        token@.len() == 0 ==> r.is_none(),
{
    const TABLE: &'static [(&'static str, usize, &'static str)] = &[
        ("один", 4, "1"), ("одна", 4, "1"), ("одно", 4, "1"),
        ("два", 3, "2"), ("две", 3, "2"),
        ("три", 3, "3"),
        ("четыре", 6, "4"),
        ("пять", 4, "5"),
        ("шесть", 5, "6"),
        ("семь", 4, "7"),
        ("восемь", 6, "8"),
        ("девять", 6, "9"),
        ("десять", 6, "10"),
        ("одиннадцать", 11, "11"),
        ("двенадцать", 10, "12"),
        ("тринадцать", 10, "13"),
        ("четырнадцать", 12, "14"),
        ("пятнадцать", 10, "15"),
        ("двадцать", 8, "20"),
        ("тридцать", 8, "30"),
        ("сорок", 5, "40"),
        ("пятьдесят", 9, "50"),
        ("сто", 3, "100"),
    ];
    let bytes = token.as_bytes();
    let len = bytes.len();
    let mut i: usize = 0;
    while i < TABLE.len()
        invariant
            i <= TABLE.len(),
    {
        let (word, word_len, digit) = TABLE[i];
        if len == word_len {
            let wb = word.as_bytes();
            let mut j: usize = 0;
            let mut matched: bool = true;
            while j < wb.len()
                invariant
                    j <= wb.len(),
                    wb.len() == word_len,
                    bytes.len() == len,
            {
                let a = wb[j];
                let b = bytes[j];
                if !(a == b || a.to_ascii_lowercase() == b.to_ascii_lowercase()) {
                    matched = false;
                    break;
                }
                j = j + 1;
            }
            if matched {
                return Some(digit);
            }
        }
        i = i + 1;
    }
    None
}

fn main() {}

} // verus!
EOF

echo '=== 1. Verus' >> "$OUT"
cd /tmp/verusnw || exit 2
timeout 600 /opt/verus/verus-run main.rs >> "$OUT" 2>&1
echo "exit: $?" >> "$OUT"
echo DONE >> "$OUT"
