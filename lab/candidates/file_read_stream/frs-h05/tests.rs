include!("source.rs");

fn case_0(failures: &mut usize) -> usize {
    let input: &[u8] = &[0x61, 0x0a];
    let request = Request {
        line_count: 1,
        max_bytes_read: 1,
    };
    match stream(input, &request) {
        Ok(output) => {
            println!("[FAIL] main: ожидался отказ K4_RESOURCE_LIMIT, получен ok");
            *failures += 1;
            1
        }
        Err(code) => {
            if !code.starts_with("K4_RESOURCE_LIMIT:") {
                println!("[FAIL] main: code={} expected=K4_RESOURCE_LIMIT", code);
                *failures += 1;
            }
            1
        }
    }
}

fn run_frs_h05(failures: &mut usize) -> usize {
    0
    + case_0(failures)
}

fn main() {
    let mut failures = 0usize;
    let mut cases = 0usize;
    {
        let before = failures;
        cases += run_frs_h05(&mut failures);
        println!("spec=frs-h05 cases=1 failures={}", failures - before);
    }
    if cases != 1 {
        println!("[FAIL] cases={} expected=1", cases);
        failures += 1;
    }
    println!("total_cases=1 failures={}", failures);
    if failures > 0 { std::process::exit(1); }
}
