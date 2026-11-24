use std::fs;
use std::path::PathBuf;
use std::process::{Command, Output};
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT: AtomicUsize = AtomicUsize::new(0);

fn fixture() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "hs-grants-cli-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&path).unwrap();
    path
}

fn check(path: &PathBuf) -> Output {
    Command::new(env!("CARGO_BIN_EXE_hs-core"))
        .arg("grants-check")
        .arg(path)
        .output()
        .unwrap()
}

fn text(output: &Output) -> String {
    format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    )
}

#[test]
fn grants_check_has_nonzero_missing_and_invalid_and_valid_deny_all() {
    let dir = fixture();
    let path = dir.join("tools.json");

    let output = check(&path);
    assert!(!output.status.success(), "Missing обязан быть фатальным");
    assert!(text(&output).contains("GRANTS_STATE=Missing"), "{output:?}");

    for bad in [
        "{",
        "{}",
        "null",
        r#""net""#,
        r#"["net",7]"#,
        r#"["net","unknown"]"#,
    ] {
        fs::write(&path, bad).unwrap();
        let output = check(&path);
        assert!(!output.status.success(), "Invalid принят: {bad}");
        assert!(
            text(&output).contains("GRANTS_STATE=Invalid"),
            "{bad}: {output:?}"
        );
    }

    let output = check(&dir);
    assert!(
        !output.status.success(),
        "ошибка чтения не является Missing/успехом"
    );
    assert!(text(&output).contains("GRANTS_STATE=Invalid"), "{output:?}");

    fs::write(&path, r#"["net"]"#).unwrap();
    let output = check(&path);
    assert!(output.status.success(), "{output:?}");
    let body = text(&output);
    assert!(body.contains("GRANTS_STATE=Valid"), "{body}");
    assert!(body.contains("GRANTS_COUNT=1"), "{body}");
    assert!(body.contains("GRANTS_DENY_ALL=0"), "{body}");

    fs::write(&path, "[]").unwrap();
    let output = check(&path);
    assert!(
        output.status.success(),
        "пустой список — валидный deny-all: {output:?}"
    );
    let body = text(&output);
    assert!(body.contains("GRANTS_STATE=Valid"), "{body}");
    assert!(body.contains("GRANTS_COUNT=0"), "{body}");
    assert!(body.contains("GRANTS_DENY_ALL=1"), "{body}");

    fs::remove_dir_all(dir).unwrap();
}
