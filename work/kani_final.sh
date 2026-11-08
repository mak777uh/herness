#!/usr/bin/env bash
# Kani: harness на массивах байтов, а не на String (String не реализует kani::Arbitrary).
OUT=/mnt/c/111/herness/work/kani-final.txt
: > "$OUT"

export PATH="/opt/rust-nightly/tc/bin:/opt/kani/kani-0.68.0/bin:$PATH"
export KANI_HOME=/opt/kani/kani-0.68.0
export LD_LIBRARY_PATH="/opt/rust-nightly/tc/lib:/opt/rust-nightly/tc/lib/rustlib/x86_64-unknown-linux-gnu/lib"

echo '=== окружение' >> "$OUT"
kani --version >> "$OUT" 2>&1

rm -rf /tmp/kanicheck
mkdir -p /tmp/kanicheck/src
cat > /tmp/kanicheck/src/main.rs <<'EOF'
// Три функции из core-rs/src/loopmod.rs, вырезанные для проверки Kani.

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
        let bytes: [u8; 8] = kani::any();
        if let Ok(s) = std::str::from_utf8(&bytes) {
            let _ = number_word(s);
        }
    }

    /// normalize_token не паникует ни на какой строке.
    #[kani::proof]
    fn normalize_token_never_panics() {
        let bytes: [u8; 8] = kani::any();
        if let Ok(s) = std::str::from_utf8(&bytes) {
            let _ = normalize_token(s);
        }
    }

    /// resource_matches не паникует ни на какой паре строк.
    #[kani::proof]
    fn resource_matches_never_panics() {
        let p: [u8; 6] = kani::any();
        let r: [u8; 6] = kani::any();
        if let (Ok(ps), Ok(rs)) = (std::str::from_utf8(&p), std::str::from_utf8(&r)) {
            let _ = resource_matches(ps, rs);
        }
    }

    /// resource_matches: «/mnt/**» не совпадает с чужим путём.
    #[kani::proof]
    fn deny_outside_prefix() {
        let r: [u8; 6] = kani::any();
        if let Ok(rs) = std::str::from_utf8(&r) {
            kani::assume(!rs.starts_with("/mnt"));
            assert!(!resource_matches("/mnt/**", rs));
        }
    }
}
EOF

echo '=== прогон' >> "$OUT"
cd /tmp/kanicheck || exit 2
for h in number_word_never_panics normalize_token_never_panics resource_matches_never_panics deny_outside_prefix; do
  echo "--- $h" >> "$OUT"
  timeout 400 kani src/main.rs --harness "$h" >> "$OUT" 2>&1
  echo "$h: $?" >> "$OUT"
done
echo DONE >> "$OUT"
