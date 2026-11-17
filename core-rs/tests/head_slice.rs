//! Интеграционный контракт HEAD-SLICE-R1: fixture, admission и точные коды.
//!
//! Это не QEMU-прогон; измерительная комната и хост/гость — `bin/head_slice.py`.
//! Здесь фиксируется, что публичный API `head` держит положительный контроль и
//! границу symlink/root без доступа к приватным тестовым помощникам.

#![cfg(target_os = "linux")]

use std::collections::BTreeMap;

use hs_core::admission::{digest_bytes, VerifiedAdmission, DIGEST_FIELDS};
use hs_core::head::{file_read_stream, HeadRequest, PathRef};

fn fixture() -> Vec<u8> {
    std::fs::read("../lab/fixtures/model_visible/head-slice.txt").unwrap()
}

fn manifest(fixture: &[u8]) -> Vec<u8> {
    serde_json::to_vec(&serde_json::json!({
        "schema_version": "fixture-manifest-v1",
        "root_ref": "room:input",
        "fixture_root": "fixtures",
        "accepted_classes": ["model_visible"],
        "files": [{
            "path": "head-slice.txt",
            "bytes": fixture.len(),
            "lines": 10,
            "sha256": digest_bytes(fixture),
            "data_class": "model_visible",
        }],
    }))
    .unwrap()
}

fn admission(manifest: &[u8]) -> VerifiedAdmission {
    let mut digests = BTreeMap::new();
    for field in DIGEST_FIELDS {
        digests.insert(field.to_string(), digest_bytes(manifest));
    }
    VerifiedAdmission {
        tool: "head".to_string(),
        epoch: 1,
        seq: 1,
        test_only: true,
        digests,
    }
}

fn room(name: &str) -> std::path::PathBuf {
    let root = std::env::temp_dir().join(format!(
        "herness-integration-head-{}-{name}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(root.join("fixtures")).unwrap();
    root
}

#[test]
fn positive_is_exactly_three_lines_and_144_bytes() {
    let root = room("positive");
    let fixture = fixture();
    std::fs::write(root.join("fixtures/head-slice.txt"), &fixture).unwrap();
    let manifest = manifest(&fixture);
    let admission = admission(&manifest);
    let request = HeadRequest {
        path_ref: PathRef::new("room:input", &["fixtures", "head-slice.txt"]),
        line_count: 3,
        max_bytes_read: 4096,
    };
    let output = file_read_stream(&root, &manifest, &request, Some(&admission)).unwrap();
    assert_eq!(output.lines.len(), 3);
    assert_eq!(output.bytes_read, 144);
    assert!(output.truncated);
    assert_eq!(output.stop_reason.as_str(), "line_cap");
    assert!(output.bytes_received <= 4096);
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn symlink_outside_is_refused_and_canary_never_appears() {
    let root = room("symlink");
    let fixture = fixture();
    std::fs::write(root.join("fixtures/head-slice.txt"), &fixture).unwrap();
    let canary = b"CANARY-HEAD-SLICE-INTEGRATION";
    let outside = root.join("outside-canary");
    std::fs::write(&outside, canary).unwrap();
    std::os::unix::fs::symlink(&outside, root.join("fixtures/escape")).unwrap();
    let manifest = serde_json::to_vec(&serde_json::json!({
        "schema_version": "fixture-manifest-v1",
        "root_ref": "room:input",
        "fixture_root": "fixtures",
        "accepted_classes": ["model_visible"],
        "files": [
            {
                "path": "head-slice.txt",
                "bytes": fixture.len(),
                "lines": 10,
                "sha256": digest_bytes(&fixture),
                "data_class": "model_visible",
            },
            {
                "path": "escape",
                "bytes": canary.len(),
                "lines": 1,
                "sha256": digest_bytes(canary),
                "data_class": "model_visible",
            },
        ],
    }))
    .unwrap();
    let admission = admission(&manifest);
    let request = HeadRequest {
        path_ref: PathRef::new("room:input", &["fixtures", "escape"]),
        line_count: 3,
        max_bytes_read: 4096,
    };
    let error = file_read_stream(&root, &manifest, &request, Some(&admission)).unwrap_err();
    assert!(error.starts_with("S6_CLOSURE_BREACH:"), "{error}");
    assert!(!error.contains("CANARY"));
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn missing_admission_is_k11_before_reading() {
    let root = room("admission");
    let fixture = fixture();
    std::fs::write(root.join("fixtures/head-slice.txt"), &fixture).unwrap();
    let manifest = manifest(&fixture);
    let request = HeadRequest {
        path_ref: PathRef::new("room:input", &["fixtures", "head-slice.txt"]),
        line_count: 3,
        max_bytes_read: 4096,
    };
    let error = file_read_stream(&root, &manifest, &request, None).unwrap_err();
    assert!(error.starts_with("K11_ADMISSION_REQUIRED:"), "{error}");
    let _ = std::fs::remove_dir_all(root);
}
