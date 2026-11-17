include!("source.rs");

fn case_0(failures: &mut usize) -> usize {
    let input: &[u8] = &[0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6a, 0x0a];
    let request = Request {
        line_count: 5,
        max_bytes_read: 5,
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

fn case_1(failures: &mut usize) -> usize {
    let input: &[u8] = &[0x61, 0x0a];
    let request = Request {
        line_count: 201,
        max_bytes_read: 5,
    };
    match stream(input, &request) {
        Ok(output) => {
            println!("[FAIL] schema-line-count: ожидался отказ S1_SCHEMA, получен ok");
            *failures += 1;
            1
        }
        Err(code) => {
            if !code.starts_with("S1_SCHEMA:") {
                println!("[FAIL] schema-line-count: code={} expected=S1_SCHEMA", code);
                *failures += 1;
            }
            1
        }
    }
}

fn run_frs_a07(failures: &mut usize) -> usize {
    0
    + case_0(failures)
    + case_1(failures)
}

fn main() {
    let mut failures = 0usize;
    let mut cases = 0usize;
    {
        let before = failures;
        cases += run_frs_a07(&mut failures);
        println!("spec=frs-a07 cases=2 failures={}", failures - before);
    }
    if cases != 2 {
        println!("[FAIL] cases={} expected=2", cases);
        failures += 1;
    }
    println!("total_cases=2 failures={}", failures);
    if failures > 0 { std::process::exit(1); }
}
