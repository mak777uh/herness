//! Ядро харнесса: канонизация, хеш-цепочка журнала, печать методологии.
//!
//! Контракт с эталонной реализацией на Python заморожен в `tests/vectors/*.json`.
//! Расхождение — дефект одной из реализаций, а не «другая трактовка».

pub mod clock;
pub mod journal;

use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

/// Маркер, после которого начинается печать (не входит в хеш).
pub const SEAL_MARKER: &str = "## Seal";

/// Канонический JSON: ключи отсортированы, без пробелов, UTF-8 без экранирования.
pub fn canonical_json(value: &Value) -> String {
    serde_json::to_string(value).expect("значение сериализуемо")
}

/// Канонический префикс файла: CRLF/CR -> LF, отсечение после маркера, `rstrip` + `\n`.
pub fn canonical_seal(text: &str) -> String {
    let normalized = text.replace("\r\n", "\n").replace('\r', "\n");
    let prefix = match normalized.find(SEAL_MARKER) {
        Some(index) => &normalized[..index],
        None => &normalized[..],
    };
    format!("{}\n", prefix.trim_end())
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hex::encode(hasher.finalize())
}

pub fn seal_hash(text: &str) -> String {
    sha256_hex(canonical_seal(text).as_bytes())
}

/// Хеш события журнала: SHA-256 по каноническому JSON события вместе с `prev`.
pub fn event_hash(event: &Value, prev: &str) -> String {
    let mut object: Map<String, Value> = event.as_object().cloned().unwrap_or_default();
    object.insert("prev".to_string(), Value::String(prev.to_string()));
    sha256_hex(canonical_json(&Value::Object(object)).as_bytes())
}

/// Цепочка: (prev, hash) для каждого события.
pub fn chain(events: &[Value]) -> Vec<(String, String)> {
    let mut result = Vec::with_capacity(events.len());
    let mut prev = String::new();
    for event in events {
        let digest = event_hash(event, &prev);
        result.push((prev.clone(), digest.clone()));
        prev = digest;
    }
    result
}
