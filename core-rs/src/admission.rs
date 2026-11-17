//! Допуск чужого кода (K11): канонический JSON, detached Ed25519 и точные байты.
//!
//! Контракт заморожен в `docs/DECISIONS-R8-2026-11-17.md` (A01/Q15):
//! JCS-подмножество без float, доменный префикс `herness-admission-v1`,
//! raw Ed25519 (RFC 8032), sidecar-подпись, exact-byte digest.
//!
//! Модуль намеренно тонкий: он проверяет подпись, срок, epoch/seq/prev и наличие
//! digest-полей. Полная семантика карточки — на promoter (Q11). Любая ошибка
//! возвращается как `K11_ADMISSION_REQUIRED: ...`; частично проверенный манифест
//! не становится допуском.

use std::collections::BTreeMap;
use std::fmt::{self, Write as _};
use std::io::Read;
use std::path::Path;

use ed25519_dalek::{Signature, VerifyingKey};
use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

/// Домен подписи. Отделяет admission-подписи от любых других подписей тем же ключом.
pub const DOMAIN: &[u8] = b"herness-admission-v1";
/// Хеш пустой цепочки: первый admission обязан ссылаться на него.
pub const GENESIS: &str = "sha256:ad91748e7797e06cd9bade33556abe349c5b6f8ad15fd51384ffe1822a889b68";
/// JCS-числа — IEEE-754 double: за пределами ±(2^53-1) парсеры расходятся.
pub const SAFE_INT: u64 = 9_007_199_254_740_991;
/// Поля exact-byte привязки. Все обязательны; пропуск — K11.
pub const DIGEST_FIELDS: [&str; 6] = [
    "card_digest",
    "source_digest",
    "binary_digest",
    "fixture_digest",
    "policy_digest",
    "room_digest",
];

#[derive(Debug, Clone)]
pub struct VerifiedAdmission {
    pub tool: String,
    pub epoch: i64,
    pub seq: i64,
    pub test_only: bool,
    pub digests: BTreeMap<String, String>,
}

fn refuse(reason: impl AsRef<str>) -> String {
    format!("K11_ADMISSION_REQUIRED: {}", reason.as_ref())
}

fn sha256(bytes: &[u8]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hasher.finalize().into()
}

/// SHA-256 в формате `sha256:<lowercase hex>`.
pub fn digest_bytes(bytes: &[u8]) -> String {
    format!("sha256:{}", hex::encode(sha256(bytes)))
}

/// Потоковый exact-byte digest файла. Файл не загружается целиком.
pub fn digest_file(path: &Path) -> Result<String, String> {
    let mut file = std::fs::File::open(path)
        .map_err(|error| refuse(format!("нет файла {}: {error}", path.display())))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|error| refuse(format!("не прочитать {}: {error}", path.display())))?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(format!("sha256:{}", hex::encode(hasher.finalize())))
}

/// Сравнивает exact-byte digest с ожидаемым. Один изменённый байт — K11.
pub fn verify_file_digest(expected: &str, path: &Path) -> Result<(), String> {
    let actual = digest_file(path)?;
    if actual != expected {
        return Err(refuse(format!(
            "{} не совпадает с допущенными байтами: ожидалось {expected}, получено {actual}",
            path.display()
        )));
    }
    Ok(())
}

fn write_escaped(text: &str, out: &mut Vec<u8>) {
    out.push(b'"');
    for ch in text.chars() {
        match ch {
            '"' => out.extend_from_slice(b"\\\""),
            '\\' => out.extend_from_slice(b"\\\\"),
            '\u{08}' => out.extend_from_slice(b"\\b"),
            '\u{0c}' => out.extend_from_slice(b"\\f"),
            '\n' => out.extend_from_slice(b"\\n"),
            '\r' => out.extend_from_slice(b"\\r"),
            '\t' => out.extend_from_slice(b"\\t"),
            control if (control as u32) < 0x20 => {
                let mut escaped = String::new();
                write!(&mut escaped, "\\u{:04x}", control as u32)
                    .expect("запись в String не падает");
                out.extend_from_slice(escaped.as_bytes());
            }
            other => {
                let mut encoded = [0u8; 4];
                out.extend_from_slice(other.encode_utf8(&mut encoded).as_bytes());
            }
        }
    }
    out.push(b'"');
}

fn write_canonical(value: &Value, out: &mut Vec<u8>) -> Result<(), String> {
    match value {
        Value::Null => out.extend_from_slice(b"null"),
        Value::Bool(true) => out.extend_from_slice(b"true"),
        Value::Bool(false) => out.extend_from_slice(b"false"),
        Value::Number(number) => {
            if let Some(value) = number.as_i64() {
                if value.unsigned_abs() > SAFE_INT {
                    return Err(refuse(format!(
                        "целое {value} вне безопасного диапазона JCS (±{SAFE_INT})"
                    )));
                }
                out.extend_from_slice(value.to_string().as_bytes());
            } else if let Some(value) = number.as_u64() {
                if value > SAFE_INT {
                    return Err(refuse(format!(
                        "целое {value} вне безопасного диапазона JCS (±{SAFE_INT})"
                    )));
                }
                out.extend_from_slice(value.to_string().as_bytes());
            } else {
                return Err(refuse("float в каноническом JSON запрещён"));
            }
        }
        Value::String(text) => write_escaped(text, out),
        Value::Array(items) => {
            out.push(b'[');
            for (index, item) in items.iter().enumerate() {
                if index > 0 {
                    out.push(b',');
                }
                write_canonical(item, out)?;
            }
            out.push(b']');
        }
        Value::Object(object) => {
            // JCS: ключи сортируются. Подмножество v0 — ASCII-ключи, поэтому
            // порядок UTF-8 совпадает с порядком UTF-16 code units.
            let mut keys: Vec<&String> = object.keys().collect();
            keys.sort();
            out.push(b'{');
            for (index, key) in keys.iter().enumerate() {
                if index > 0 {
                    out.push(b',');
                }
                if !key.is_ascii() {
                    return Err(refuse("не-ASCII ключ не входит в JCS-подмножество v0"));
                }
                write_escaped(key, out);
                out.push(b':');
                write_canonical(&object[*key], out)?;
            }
            out.push(b'}');
        }
    }
    Ok(())
}

/// JCS-подмножество v0: без float, ключи отсортированы, без пробелов, UTF-8.
pub fn canonical_json_bytes(value: &Value) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    write_canonical(value, &mut out)?;
    Ok(out)
}

/// Строгий JSON-объект: повтор ключа, float и целое вне safe range — отказ.
///
/// `serde_json::Value` сам по себе теряет повторы ключей (побеждает последний),
/// поэтому разбор идёт через visitor, а не через `from_slice::<Value>`.
struct StrictValue(Value);

impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(StrictVisitor)
    }
}

struct StrictVisitor;

impl<'de> Visitor<'de> for StrictVisitor {
    type Value = StrictValue;

    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        formatter.write_str("JSON в JCS-подмножестве v0")
    }

    fn visit_bool<E: de::Error>(self, value: bool) -> Result<Self::Value, E> {
        Ok(StrictValue(Value::Bool(value)))
    }

    fn visit_i64<E: de::Error>(self, value: i64) -> Result<Self::Value, E> {
        if value.unsigned_abs() > SAFE_INT {
            return Err(de::Error::custom(format!(
                "целое {value} вне безопасного диапазона JCS (±{SAFE_INT})"
            )));
        }
        Ok(StrictValue(Value::from(value)))
    }

    fn visit_u64<E: de::Error>(self, value: u64) -> Result<Self::Value, E> {
        if value > SAFE_INT {
            return Err(de::Error::custom(format!(
                "целое {value} вне безопасного диапазона JCS (±{SAFE_INT})"
            )));
        }
        Ok(StrictValue(Value::from(value)))
    }

    fn visit_f64<E: de::Error>(self, _value: f64) -> Result<Self::Value, E> {
        Err(de::Error::custom("float в каноническом JSON запрещён"))
    }

    fn visit_str<E: de::Error>(self, value: &str) -> Result<Self::Value, E> {
        Ok(StrictValue(Value::String(value.to_string())))
    }

    fn visit_string<E: de::Error>(self, value: String) -> Result<Self::Value, E> {
        Ok(StrictValue(Value::String(value)))
    }

    fn visit_none<E: de::Error>(self) -> Result<Self::Value, E> {
        Ok(StrictValue(Value::Null))
    }

    fn visit_unit<E: de::Error>(self) -> Result<Self::Value, E> {
        Ok(StrictValue(Value::Null))
    }

    fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        Deserialize::deserialize(deserializer)
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::new();
        while let Some(value) = sequence.next_element::<StrictValue>()? {
            values.push(value.0);
        }
        Ok(StrictValue(Value::Array(values)))
    }

    fn visit_map<A>(self, mut access: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut values = Map::new();
        while let Some(key) = access.next_key::<String>()? {
            if values.contains_key(&key) {
                return Err(de::Error::custom(format!(
                    "повтор ключа {key:?} в JSON запрещён"
                )));
            }
            let value = access.next_value::<StrictValue>()?;
            values.insert(key, value.0);
        }
        Ok(StrictValue(Value::Object(values)))
    }
}

fn parse_document(bytes: &[u8], what: &str) -> Result<Value, String> {
    serde_json::from_slice::<StrictValue>(bytes)
        .map(|value| value.0)
        .map_err(|error| refuse(format!("{what} не разбирается как JSON: {error}")))
}

/// Публичная точка для differential-проверок: разбор в строгом JCS-подмножестве.
pub fn strict_json_value(bytes: &[u8], what: &str) -> Result<Value, String> {
    parse_document(bytes, what)
}

fn object<'a>(value: &'a Value, what: &str) -> Result<&'a Map<String, Value>, String> {
    value
        .as_object()
        .ok_or_else(|| refuse(format!("{what} должен быть объектом")))
}

fn text<'a>(object: &'a Map<String, Value>, key: &str) -> Result<&'a str, String> {
    object
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| refuse(format!("нет строкового поля {key}")))
}

fn integer(object: &Map<String, Value>, key: &str) -> Result<i64, String> {
    let value = object
        .get(key)
        .and_then(Value::as_i64)
        .ok_or_else(|| refuse(format!("нет целого поля {key}")))?;
    if value.unsigned_abs() > SAFE_INT {
        return Err(refuse(format!(
            "целое {value} вне безопасного диапазона JCS (±{SAFE_INT})"
        )));
    }
    Ok(value)
}

fn boolean(object: &Map<String, Value>, key: &str) -> Result<bool, String> {
    object
        .get(key)
        .and_then(Value::as_bool)
        .ok_or_else(|| refuse(format!("нет булева поля {key}")))
}

fn valid_digest(value: &str) -> bool {
    let Some(hex_part) = value.strip_prefix("sha256:") else {
        return false;
    };
    hex_part.len() == 64
        && hex_part
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn parse_rfc3339_utc(value: &str) -> Option<i64> {
    // Строгий UTC-формат v0: YYYY-MM-DDTHH:MM:SSZ. Смещения не принимаются:
    // два парсера (Rust/Python) должны читать срок одинаково.
    let bytes = value.as_bytes();
    if bytes.len() != 20
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || bytes[19] != b'Z'
    {
        return None;
    }
    let number = |from: usize, to: usize| -> Option<i64> {
        let part = &value[from..to];
        if part.bytes().all(|byte| byte.is_ascii_digit()) {
            part.parse().ok()
        } else {
            None
        }
    };
    let (year, month, day) = (number(0, 4)?, number(5, 7)?, number(8, 10)?);
    let (hour, minute, second) = (number(11, 13)?, number(14, 16)?, number(17, 19)?);
    if !(1..=12).contains(&month)
        || day < 1
        || hour > 23
        || minute > 59
        || second > 59
        || day > days_in_month(year, month)
    {
        return None;
    }
    Some(days_from_civil(year, month, day) * 86_400 + hour * 3_600 + minute * 60 + second)
}

fn is_leap(year: i64) -> bool {
    (year % 4 == 0 && year % 100 != 0) || year % 400 == 0
}

fn days_in_month(year: i64, month: i64) -> i64 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if is_leap(year) => 29,
        2 => 28,
        _ => 0,
    }
}

// Гражданская дата -> дни от 1970-01-01 (Howard Hinnant).
fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let year = if month <= 2 { year - 1 } else { year };
    let era = if year >= 0 { year } else { year - 399 } / 400;
    let year_of_era = year - era * 400;
    let month_prime = (month + 9) % 12;
    let day_of_year = (153 * month_prime + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * 146_097 + day_of_era - 719_468
}

fn anchor(value: &Value) -> Result<(String, [u8; 32], i64, Vec<i64>, String), String> {
    let object = object(value, "anchor")?;
    if text(object, "schema")? != "herness-anchor-v1" {
        return Err(refuse("anchor: ожидалась схема herness-anchor-v1"));
    }
    if text(object, "kind")? != "owner_anchor" {
        return Err(refuse("anchor: ожидался kind owner_anchor"));
    }
    let public_hex = text(object, "public_key")?;
    let public_bytes = hex::decode(public_hex)
        .map_err(|_| refuse("anchor: public_key не hex"))?;
    let public: [u8; 32] = public_bytes
        .try_into()
        .map_err(|_| refuse("anchor: public_key не 32 байта"))?;
    let fingerprint = digest_bytes(&public);
    if text(object, "key_fingerprint")? != fingerprint {
        return Err(refuse("anchor: fingerprint не совпадает с public_key"));
    }
    let min_epoch = integer(object, "min_epoch")?;
    if min_epoch < 0 {
        return Err(refuse("anchor: min_epoch отрицателен"));
    }
    let revoked: Vec<i64> = object
        .get("revoked_epochs")
        .and_then(Value::as_array)
        .ok_or_else(|| refuse("anchor: нет массива revoked_epochs"))?
        .iter()
        .map(|item| {
            item.as_i64()
                .ok_or_else(|| refuse("anchor: revoked_epochs содержит не целое"))
        })
        .collect::<Result<_, _>>()?;
    let expected_prev = match object.get("expected_prev") {
        Some(value) => value
            .as_str()
            .ok_or_else(|| refuse("anchor: expected_prev не строка"))?
            .to_string(),
        None => GENESIS.to_string(),
    };
    if !valid_digest(&expected_prev) {
        return Err(refuse("anchor: expected_prev не sha256"));
    }
    Ok((fingerprint, public, min_epoch, revoked, expected_prev))
}

/// Проверка admission. `now_unix` передаётся явно, чтобы срок проверялся
/// воспроизводимо; `allow_test_only` разрешает только тестовые манифесты и не
/// делает инструмент `active`.
pub fn verify_admission(
    manifest_bytes: &[u8],
    signature_hex: &str,
    anchor_bytes: &[u8],
    now_unix: i64,
    allow_test_only: bool,
) -> Result<VerifiedAdmission, String> {
    let manifest = parse_document(manifest_bytes, "manifest")?;
    let anchor_document = parse_document(anchor_bytes, "anchor")?;
    let (fingerprint, public, min_epoch, revoked, expected_prev) = anchor(&anchor_document)?;

    let object = object(&manifest, "manifest")?;
    if text(object, "schema")? != "herness-admission-v1" {
        return Err(refuse("manifest: ожидалась схема herness-admission-v1"));
    }
    if text(object, "kind")? != "tool_admission" {
        return Err(refuse("manifest: ожидался kind tool_admission"));
    }
    let tool = text(object, "tool")?;
    if tool.is_empty()
        || tool.len() > 64
        || !tool
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
    {
        return Err(refuse("manifest: недопустимое имя инструмента"));
    }
    if text(object, "key_fingerprint")? != fingerprint {
        return Err(refuse("manifest: key_fingerprint не совпадает с anchor"));
    }

    let mut digests = BTreeMap::new();
    for field in DIGEST_FIELDS {
        let value = text(object, field)?;
        if !valid_digest(value) {
            return Err(refuse(format!("manifest: {field} не sha256:<lowercase hex>")));
        }
        digests.insert(field.to_string(), value.to_string());
    }

    let epoch = integer(object, "epoch")?;
    let seq = integer(object, "seq")?;
    if epoch < 1 || seq < 1 {
        return Err(refuse("manifest: epoch и seq должны быть >= 1"));
    }
    if epoch < min_epoch {
        return Err(refuse(format!(
            "manifest: epoch {epoch} ниже min_epoch {min_epoch} (rollback)"
        )));
    }
    if revoked.contains(&epoch) {
        return Err(refuse(format!("manifest: epoch {epoch} отозван")));
    }
    let prev = text(object, "prev")?;
    if !valid_digest(prev) {
        return Err(refuse("manifest: prev не sha256"));
    }
    if prev != expected_prev {
        return Err(refuse("manifest: prev не совпадает с якорем (разрыв цепочки)"));
    }

    let not_before = text(object, "not_before")?;
    let not_after = text(object, "not_after")?;
    let start =
        parse_rfc3339_utc(not_before).ok_or_else(|| refuse("manifest: not_before не UTC RFC3339"))?;
    let end =
        parse_rfc3339_utc(not_after).ok_or_else(|| refuse("manifest: not_after не UTC RFC3339"))?;
    if end < start {
        return Err(refuse("manifest: not_after раньше not_before"));
    }
    if now_unix < start {
        return Err(refuse("manifest: admission ещё не вступил в силу"));
    }
    if now_unix > end {
        return Err(refuse("manifest: admission просрочен"));
    }

    let test_only = boolean(object, "test_only")?;
    if test_only && !allow_test_only {
        return Err(refuse(
            "manifest: test-only не даёт права запуска; нужен owner-подписанный admission",
        ));
    }

    let signature_bytes = hex::decode(signature_hex.trim())
        .map_err(|_| refuse("подпись не hex"))?;
    let signature = Signature::from_slice(&signature_bytes)
        .map_err(|_| refuse("подпись не 64 байта"))?;
    let key = VerifyingKey::from_bytes(&public).map_err(|_| refuse("anchor: неверный public_key"))?;

    let canonical = canonical_json_bytes(&manifest)?;
    let mut signed = Vec::with_capacity(DOMAIN.len() + 1 + canonical.len());
    signed.extend_from_slice(DOMAIN);
    signed.push(b'\n');
    signed.extend_from_slice(&canonical);
    key.verify_strict(&signed, &signature)
        .map_err(|_| refuse("подпись не соответствует манифесту и anchor"))?;

    Ok(VerifiedAdmission {
        tool: tool.to_string(),
        epoch,
        seq,
        test_only,
        digests,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};

    const SEED: [u8; 32] = [7u8; 32];

    fn anchor_bytes(key: &SigningKey, min_epoch: i64, revoked: &[i64], prev: &str) -> Vec<u8> {
        let public = key.verifying_key().to_bytes();
        let value = serde_json::json!({
            "schema": "herness-anchor-v1",
            "kind": "owner_anchor",
            "public_key": hex::encode(public),
            "key_fingerprint": digest_bytes(&public),
            "min_epoch": min_epoch,
            "revoked_epochs": revoked,
            "expected_prev": prev,
        });
        canonical_json_bytes(&value).unwrap()
    }

    fn manifest(epoch: i64, prev: &str, test_only: bool) -> Value {
        let mut digests = Map::new();
        for field in DIGEST_FIELDS {
            digests.insert(field.to_string(), Value::String(digest_bytes(field.as_bytes())));
        }
        digests.insert("schema".into(), Value::String("herness-admission-v1".into()));
        digests.insert("kind".into(), Value::String("tool_admission".into()));
        digests.insert("tool".into(), Value::String("head".into()));
        digests.insert(
            "key_fingerprint".into(),
            Value::String(digest_bytes(&SigningKey::from_bytes(&SEED).verifying_key().to_bytes())),
        );
        digests.insert("epoch".into(), Value::from(epoch));
        digests.insert("seq".into(), Value::from(1));
        digests.insert("prev".into(), Value::String(prev.into()));
        digests.insert("not_before".into(), Value::String("2026-01-01T00:00:00Z".into()));
        digests.insert("not_after".into(), Value::String("2027-01-01T00:00:00Z".into()));
        digests.insert("test_only".into(), Value::Bool(test_only));
        Value::Object(digests)
    }

    fn sign(value: &Value, key: &SigningKey) -> (Vec<u8>, String) {
        let bytes = canonical_json_bytes(value).unwrap();
        let mut signed = Vec::new();
        signed.extend_from_slice(DOMAIN);
        signed.push(b'\n');
        signed.extend_from_slice(&bytes);
        (bytes, hex::encode(key.sign(&signed).to_bytes()))
    }

    fn now() -> i64 {
        parse_rfc3339_utc("2026-06-01T00:00:00Z").unwrap()
    }

    #[test]
    fn canonical_json_matches_contract_subset() {
        let value = serde_json::json!({
            "b": [true, null, -3, "текст\n"],
            "a": {"z": 1, "y": "\u{1f}"},
        });
        let bytes = canonical_json_bytes(&value).unwrap();
        assert_eq!(
            String::from_utf8(bytes).unwrap(),
            "{\"a\":{\"y\":\"\\u001f\",\"z\":1},\"b\":[true,null,-3,\"текст\\n\"]}"
        );
    }

    #[test]
    fn canonical_json_rejects_float() {
        let value = serde_json::json!({"x": 1.5});
        assert!(canonical_json_bytes(&value).unwrap_err().starts_with("K11_"));
    }

    #[test]
    fn canonical_json_rejects_big_int_and_keeps_boundary() {
        let boundary = serde_json::json!({"x": SAFE_INT});
        assert_eq!(
            canonical_json_bytes(&boundary).unwrap(),
            b"{\"x\":9007199254740991}"
        );
        let big = serde_json::json!({"x": SAFE_INT + 1});
        let error = canonical_json_bytes(&big).unwrap_err();
        assert!(error.contains("безопасного диапазона"), "{error}");
        let negative = serde_json::json!({"x": -(SAFE_INT as i64) - 1});
        let error = canonical_json_bytes(&negative).unwrap_err();
        assert!(error.contains("безопасного диапазона"), "{error}");
    }

    #[test]
    fn duplicate_keys_are_rejected_before_signature() {
        let key = SigningKey::from_bytes(&SEED);
        let anchor = anchor_bytes(&key, 1, &[], GENESIS);
        let (bytes, signature) = sign(&manifest(1, GENESIS, true), &key);
        let mut duplicate = bytes.clone();
        duplicate.pop();
        duplicate.extend_from_slice(b",\"test_only\":true}");
        let error = verify_admission(&duplicate, &signature, &anchor, now(), true).unwrap_err();
        assert!(error.contains("повтор ключа"), "{error}");

        let mut duplicate_anchor = anchor.clone();
        duplicate_anchor.pop();
        duplicate_anchor.extend_from_slice(b",\"min_epoch\":1}");
        let error =
            verify_admission(&bytes, &signature, &duplicate_anchor, now(), true).unwrap_err();
        assert!(error.contains("повтор ключа"), "{error}");
    }

    #[test]
    fn parse_document_rejects_big_int() {
        let error = parse_document(b"{\"seq\":9007199254740993}", "manifest").unwrap_err();
        assert!(error.contains("безопасного диапазона"), "{error}");
    }

    #[test]
    fn accepts_signed_test_only_manifest() {
        let key = SigningKey::from_bytes(&SEED);
        let anchor_bytes = anchor_bytes(&key, 1, &[], GENESIS);
        let (bytes, signature) = sign(&manifest(1, GENESIS, true), &key);
        let verified =
            verify_admission(&bytes, &signature, &anchor_bytes, now(), true).unwrap();
        assert_eq!(verified.tool, "head");
        assert_eq!(verified.epoch, 1);
        assert!(verified.test_only);
        assert_eq!(verified.digests.len(), 6);
    }

    #[test]
    fn test_only_requires_explicit_permission() {
        let key = SigningKey::from_bytes(&SEED);
        let anchor = anchor_bytes(&key, 1, &[], GENESIS);
        let (bytes, signature) = sign(&manifest(1, GENESIS, true), &key);
        let error = verify_admission(&bytes, &signature, &anchor, now(), false).unwrap_err();
        assert!(error.contains("test-only"), "{error}");
    }

    #[test]
    fn one_changed_byte_in_manifest_breaks_signature() {
        let key = SigningKey::from_bytes(&SEED);
        let anchor = anchor_bytes(&key, 1, &[], GENESIS);
        let (mut bytes, signature) = sign(&manifest(1, GENESIS, true), &key);
        let position = bytes
            .windows(4)
            .position(|window| window == b"head")
            .expect("имя инструмента в манифесте");
        bytes[position] = b'h';
        bytes[position + 1] = b'e';
        bytes[position + 2] = b'a';
        bytes[position + 3] = b'd';
        bytes[position + 2] = b'a';
        bytes[position + 3] = b'f';
        let error = verify_admission(&bytes, &signature, &anchor, now(), true).unwrap_err();
        assert!(error.starts_with("K11_"), "{error}");
    }

    #[test]
    fn expired_and_not_yet_valid_are_k11() {
        let key = SigningKey::from_bytes(&SEED);
        let anchor = anchor_bytes(&key, 1, &[], GENESIS);
        let (bytes, signature) = sign(&manifest(1, GENESIS, true), &key);
        assert!(verify_admission(&bytes, &signature, &anchor, 1_800_000_000, true)
            .unwrap_err()
            .contains("просрочен"));
        assert!(verify_admission(&bytes, &signature, &anchor, 1, true)
            .unwrap_err()
            .contains("не вступил"));
    }

    #[test]
    fn revoked_epoch_and_min_epoch_are_k11() {
        let key = SigningKey::from_bytes(&SEED);
        let (bytes, signature) = sign(&manifest(1, GENESIS, true), &key);
        let revoked = anchor_bytes(&key, 1, &[1], GENESIS);
        assert!(verify_admission(&bytes, &signature, &revoked, now(), true)
            .unwrap_err()
            .contains("отозван"));
        let raised = anchor_bytes(&key, 2, &[], GENESIS);
        assert!(verify_admission(&bytes, &signature, &raised, now(), true)
            .unwrap_err()
            .contains("min_epoch"));
    }

    #[test]
    fn wrong_anchor_wrong_prev_and_bad_signature_are_k11() {
        let key = SigningKey::from_bytes(&SEED);
        let (bytes, signature) = sign(&manifest(1, GENESIS, true), &key);
        let other = SigningKey::from_bytes(&[9u8; 32]);
        let wrong_anchor = anchor_bytes(&other, 1, &[], GENESIS);
        assert!(verify_admission(&bytes, &signature, &wrong_anchor, now(), true).is_err());

        let wrong_prev = anchor_bytes(&key, 1, &[], &digest_bytes(b"other"));
        assert!(verify_admission(&bytes, &signature, &wrong_prev, now(), true).is_err());

        let mut bad_signature = signature.clone();
        bad_signature.replace_range(0..2, "00");
        let anchor = anchor_bytes(&key, 1, &[], GENESIS);
        assert!(verify_admission(&bytes, &bad_signature, &anchor, now(), true).is_err());
    }

    #[test]
    fn missing_anchor_or_signature_is_k11() {
        let key = SigningKey::from_bytes(&SEED);
        let anchor = anchor_bytes(&key, 1, &[], GENESIS);
        let (bytes, signature) = sign(&manifest(1, GENESIS, true), &key);
        assert!(verify_admission(&bytes, "", &anchor, now(), true).is_err());
        assert!(verify_admission(&bytes, &signature, b"{}", now(), true).is_err());
        assert!(verify_admission(b"{}", &signature, &anchor, now(), true).is_err());
    }

    #[test]
    fn digest_file_detects_one_byte_change() {
        let path = std::env::temp_dir().join(format!(
            "herness-admission-digest-{}.bin",
            std::process::id()
        ));
        std::fs::write(&path, b"abcdef").unwrap();
        let digest = digest_file(&path).unwrap();
        verify_file_digest(&digest, &path).unwrap();
        std::fs::write(&path, b"abcdeg").unwrap();
        assert!(verify_file_digest(&digest, &path)
            .unwrap_err()
            .starts_with("K11_"));
        let _ = std::fs::remove_file(path);
    }

    // Вектор сгенерирован Python-реализацией (`bin/admission.py`) из seed [7; 32].
    // Он доказывает, что JCS-подмножество и Ed25519-подпись совпадают между
    // Python и Rust; при расхождении канонизации тест падает.
    const PY_MANIFEST: &str = r#"{"binary_digest":"sha256:9a3a45d01531a20e89ac6ae10b0b0beb0492acd7216a368aa062d1a5fecaf9cd","card_digest":"sha256:8367cd66fdd136bba8ba23f8805bb050dd6289401c8ec3b0be44a3c233eef90d","epoch":1,"fixture_digest":"sha256:f16d05ec6b29248d2c61adb1e9263f78e4f7bace1b955014a2d17872cfe4064d","key_fingerprint":"sha256:fe812c12f3ab4ce6ac5db69ac352f906cb1b11ef43fb33e252ef7ff552263889","kind":"tool_admission","not_after":"2027-01-01T00:00:00Z","not_before":"2026-01-01T00:00:00Z","policy_digest":"sha256:823412d1eacb67956220e532959f0104603057c88704863ca38e7cd188fda812","prev":"sha256:ad91748e7797e06cd9bade33556abe349c5b6f8ad15fd51384ffe1822a889b68","room_digest":"sha256:1f1c5b2fad778434024f1537986346927917f4755a6e7d3fd91f22653b7c3132","schema":"herness-admission-v1","seq":1,"source_digest":"sha256:41cf6794ba4200b839c53531555f0f3998df4cbb01a4d5cb0b94e3ca5e23947d","test_only":true,"tool":"head"}"#;
    const PY_ANCHOR: &str = r#"{"expected_prev":"sha256:ad91748e7797e06cd9bade33556abe349c5b6f8ad15fd51384ffe1822a889b68","key_fingerprint":"sha256:fe812c12f3ab4ce6ac5db69ac352f906cb1b11ef43fb33e252ef7ff552263889","kind":"owner_anchor","min_epoch":1,"public_key":"ea4a6c63e29c520abef5507b132ec5f9954776aebebe7b92421eea691446d22c","revoked_epochs":[],"schema":"herness-anchor-v1","test_only":true}"#;
    const PY_SIGNATURE: &str = "9981a39917c5ee0b1ebd731831894cdb9dc74e4972ee598643df8c797e6c7262120a27471665e3e05c8cfe306e05f411d03e1ceb27d4840fe4622e9c0fdec109";

    #[test]
    fn python_generated_vector_verifies_in_rust() {
        let value: Value = serde_json::from_str(PY_MANIFEST).unwrap();
        assert_eq!(
            String::from_utf8(canonical_json_bytes(&value).unwrap()).unwrap(),
            PY_MANIFEST
        );
        let now = parse_rfc3339_utc("2026-06-01T00:00:00Z").unwrap();
        let verified =
            verify_admission(PY_MANIFEST.as_bytes(), PY_SIGNATURE, PY_ANCHOR.as_bytes(), now, true)
                .unwrap();
        assert_eq!(verified.tool, "head");
        assert_eq!(verified.digests["binary_digest"], "sha256:9a3a45d01531a20e89ac6ae10b0b0beb0492acd7216a368aa062d1a5fecaf9cd");
    }
}
