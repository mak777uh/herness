//! Сверка с замороженными векторами эталонной реализации на Python.

use serde_json::Value;
use std::fs;
use std::path::PathBuf;

fn vectors_dir() -> PathBuf {
    // тесты запускаются из core-rs, векторы лежат в ../tests/vectors
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("корень репозитория")
        .join("tests")
        .join("vectors")
}

#[test]
fn journal_chain_matches_python() {
    let raw = fs::read_to_string(vectors_dir().join("journal.json")).expect("вектор журнала");
    let data: Value = serde_json::from_str(&raw).expect("валидный JSON");
    let rows = data["chain"].as_array().expect("массив chain");

    let mut prev = String::new();
    for (index, row) in rows.iter().enumerate() {
        let event = &row["event"];
        let expected_prev = row["prev"].as_str().expect("prev");
        let expected_hash = row["hash"].as_str().expect("hash");

        assert_eq!(&prev, expected_prev, "prev расходится на событии {}", index + 1);
        let digest = hs_core::event_hash(event, &prev);
        assert_eq!(&digest, expected_hash, "hash расходится на событии {}", index + 1);
        prev = digest;
    }

    let canonical = data["canonical"].as_str().expect("canonical");
    let event = &rows[1]["event"];
    assert_eq!(hs_core::canonical_json(event), canonical, "канонический JSON расходится");
}

#[test]
fn seal_matches_python() {
    let raw = fs::read_to_string(vectors_dir().join("seal.json")).expect("вектор печати");
    let cases: Value = serde_json::from_str(&raw).expect("валидный JSON");
    for case in cases.as_array().expect("массив случаев") {
        let name = case["name"].as_str().unwrap_or("?");
        let input = case["input"].as_str().expect("input");
        let canonical = case["canonical"].as_str().expect("canonical");
        let sha = case["sha256"].as_str().expect("sha256");

        assert_eq!(hs_core::canonical_seal(input), canonical, "канонизация: {}", name);
        assert_eq!(hs_core::seal_hash(input), sha, "хеш печати: {}", name);
    }
}

#[test]
fn crlf_and_lf_agree() {
    assert_eq!(hs_core::canonical_seal("тело\r\n## Seal\r\nx"), hs_core::canonical_seal("тело\n## Seal\nx"));
}
