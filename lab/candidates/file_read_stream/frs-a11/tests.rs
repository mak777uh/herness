include!("source.rs");

fn case_0(failures: &mut usize) -> usize {
    let input: &[u8] = &[0xff, 0xfe, 0x0a];
    let request = Request {
        line_count: 2,
        max_bytes_read: 100,
    };
    match stream(input, &request) {
        Ok(output) => {
            println!("[FAIL] main: ожидался отказ S12_ENCODING, получен ok");
            *failures += 1;
            1
        }
        Err(code) => {
            if !code.starts_with("S12_ENCODING:") {
                println!("[FAIL] main: code={} expected=S12_ENCODING", code);
                *failures += 1;
            }
            1
        }
    }
}

fn run_frs_a11(failures: &mut usize) -> usize {
    0
    + case_0(failures)
}

fn main() {
    let mut failures = 0usize;
    let mut cases = 0usize;
    {
        let before = failures;
        cases += run_frs_a11(&mut failures);
        println!("spec=frs-a11 cases=1 failures={}", failures - before);
    }
    if cases != 1 {
        println!("[FAIL] cases={} expected=1", cases);
        failures += 1;
    }
    println!("total_cases=1 failures={}", failures);
    if failures > 0 { std::process::exit(1); }
}
