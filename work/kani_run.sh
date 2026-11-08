#!/usr/bin/env bash
# Kani на нашем коде: проверяем три функции на переполнения и panic.
OUT=/mnt/c/111/herness/work/kani-run.txt
: > "$OUT"

export PATH="/opt/rust-nightly/tc/bin:/opt/kani/kani-0.68.0/bin:$PATH"
export KANI_HOME=/opt/kani/kani-0.68.0

echo '=== 1. Что проверяем' >> "$OUT"
mkdir -p /tmp/kanicheck/src >> "$OUT" 2>&1
cat > /tmp/kanicheck/Cargo.toml <<'EOF'
[package]
name = "kanicheck"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "kanicheck"
path = "src/main.rs"
EOF

# Копируем три функции из нашего кода: они чистые, без файловой системы.
cat > /tmp/kanicheck/src/main.rs <<'EOF'
// Три функции из core-rs/src/loopmod.rs, вырезанные для проверки Kani.
// Они чистые: не трогают файловую систему, только строки.

/// Число словом → цифра.
fn number_word(token: &str) -> Option<&'static str> {
    let lower = token.to_lowercase();
    Some(match lower.as_str() {
        "один" | "одна" | "одно" => "1",
        "два" | "две" => "2",
        "три" => "3",
        "четыре" => "4",
        "пять" => "5",
        "шесть" => "6",
        "семь" => "7",
        "восемь" => "8",
        "девять" => "9",
        "десять" => "10",
        _ => return None,
    })
}

/// Привести токен к сравнимому виду.
fn normalize_token(token: &str) -> String {
    match number_word(token) {
        Some(digit) => digit.to_string(),
        None => token.to_string(),
    }
}

/// Сравнение ресурса с шаблоном: литерально, без «любого хвоста».
fn resource_matches(pattern: &str, resource: &str) -> bool {
    if pattern == "**" {
        return true;
    }
    if let Some(prefix) = pattern.strip_suffix("/**") {
        return resource == prefix || resource.starts_with(&format!("{prefix}/"));
    }
    pattern == resource
}

fn main() {}

#[cfg(kani)]
mod proofs {
    use super::*;

    /// number_word не паникует ни на какой строке.
    #[kani::proof]
    fn number_word_never_panics() {
        let s: String = kani::any();
        kani::assume(s.len() < 100);
        let _ = number_word(&s);
    }

    /// normalize_token не паникует ни на какой строке.
    #[kani::proof]
    fn normalize_token_never_panics() {
        let s: String = kani::any();
        kani::assume(s.len() < 100);
        let _ = normalize_token(&s);
    }

    /// resource_matches не паникует ни на какой паре строк.
    #[kani::proof]
    fn resource_matches_never_panics() {
        let p: String = kani::any();
        let r: String = kani::any();
        kani::assume(p.len() < 50 && r.len() < 50);
        let _ = resource_matches(&p, &r);
    }

    /// resource_matches: «/mnt/**» не совпадает с чужим путём.
    #[kani::proof]
    fn deny_outside_prefix() {
        let r: String = kani::any();
        kani::assume(r.len() < 50);
        kani::assume(!r.starts_with("/mnt"));
        assert!(!resource_matches("/mnt/**", &r));
    }
}
EOF

echo '=== 2. Kani' >> "$OUT"
cd /tmp/kanicheck || exit 2
kani src/main.rs --harness number_word_never_panics >> "$OUT" 2>&1
echo "number_word: $?" >> "$OUT"
kani src/main.rs --harness normalize_token_never_panics >> "$OUT" 2>&1
echo "normalize_token: $?" >> "$OUT"
kani src/main.rs --harness resource_matches_never_panics >> "$OUT" 2>&1
echo "resource_matches: $?" >> "$OUT"
kani src/main.rs --harness deny_outside_prefix >> "$OUT" 2>&1
echo "deny_outside_prefix: $?" >> "$OUT"
echo DONE >> "$OUT"
