//! Дифференциальный helper: строгий разбор/JCS и verify admission.
//!
//! `canonical` читает JSON из stdin и печатает hex канонических байтов.
//! `verify` проверяет manifest/sig/anchor и печатает JSON с полями допуска.
//! Любая ошибка — код 2 и `K11_...` в stderr; успех — код 0.

use std::io::Read;
use std::path::Path;

use hs_core::admission;

fn fail(message: String) -> ! {
    eprintln!("{message}");
    std::process::exit(2);
}

fn read_stdin() -> Vec<u8> {
    let mut input = Vec::new();
    std::io::stdin()
        .read_to_end(&mut input)
        .unwrap_or_else(|error| fail(format!("stdin: {error}")));
    input
}

fn read_file(path: &str, what: &str) -> Vec<u8> {
    std::fs::read(Path::new(path))
        .unwrap_or_else(|error| fail(format!("{what} {path}: {error}")))
}

fn main() {
    let mut arguments = std::env::args().skip(1);
    let command = arguments.next().unwrap_or_default();
    match command.as_str() {
        "canonical" => {
            let input = read_stdin();
            let value = admission::strict_json_value(&input, "input")
                .unwrap_or_else(|error| fail(error));
            let bytes = admission::canonical_json_bytes(&value)
                .unwrap_or_else(|error| fail(error));
            println!("{}", hex::encode(bytes));
        }
        "verify" => {
            let manifest_path = arguments
                .next()
                .unwrap_or_else(|| fail("verify: нет пути manifest".to_string()));
            let sig_path = arguments
                .next()
                .unwrap_or_else(|| fail("verify: нет пути sig".to_string()));
            let anchor_path = arguments
                .next()
                .unwrap_or_else(|| fail("verify: нет пути anchor".to_string()));
            let now_text = arguments
                .next()
                .unwrap_or_else(|| fail("verify: нет now_unix".to_string()));
            let now: i64 = now_text
                .parse()
                .unwrap_or_else(|error| fail(format!("verify: now_unix: {error}")));
            let allow_test_only = matches!(
                arguments.next().as_deref(),
                Some("1") | Some("true") | Some("yes")
            );
            let signature = String::from_utf8(read_file(&sig_path, "sig"))
                .unwrap_or_else(|error| fail(format!("sig не UTF-8: {error}")));
            let verified = admission::verify_admission(
                &read_file(&manifest_path, "manifest"),
                &signature,
                &read_file(&anchor_path, "anchor"),
                now,
                allow_test_only,
            )
            .unwrap_or_else(|error| fail(error));
            println!(
                "{}",
                serde_json::json!({
                    "tool": verified.tool,
                    "epoch": verified.epoch,
                    "seq": verified.seq,
                    "test_only": verified.test_only,
                    "digests": verified.digests,
                })
            );
        }
        _ => fail("usage: canonical_check canonical|verify ...".to_string()),
    }
}
