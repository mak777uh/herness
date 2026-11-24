use hs_core::host_event::project_events;
use serde_json::Value;

#[test]
fn python_rust_projection_differential() {
    let fixture: Value = serde_json::from_str(include_str!("w07b_diff_cases.json")).unwrap();
    let session = fixture["session"].as_str().unwrap();
    let cases = fixture["cases"].as_array().unwrap();
    let mut events = 0usize;
    for (index, case) in cases.iter().enumerate() {
        let lines: Vec<&str> = case["lines"].as_array().unwrap().iter().map(|line| line.as_str().unwrap()).collect();
        events += lines.len();
        let local: Vec<(&str, &str)> = lines.iter().map(|line| line.split_once(' ').unwrap()).collect();
        let actual = project_events(session, local);
        if case.get("error").is_some() {
            assert!(actual.is_err(), "case {index}: Python error but Rust accepted {lines:?}");
        } else {
            let expected = &case["expected"];
            assert_eq!(actual.as_ref().unwrap(), expected, "case {index}: {lines:?}");
        }
    }
    println!("projection differential: {cases} sequences / {events} events matched");
}
