include!("source.rs");

fn case_0(failures: &mut usize) -> usize {
    let input: &[u8] = &[0x61, 0x61, 0x0a, 0x62, 0x62, 0x62, 0x62, 0x62, 0x62, 0x0a, 0x63, 0x63, 0x0a];
    let request = Request {
        line_count: 5,
        max_bytes_read: 10,
    };
    match stream(input, &request) {
        Ok(output) => {
            let expected_lines: Vec<Vec<u8>> = vec![vec![0x61, 0x61], vec![0x62, 0x62, 0x62, 0x62, 0x62, 0x62]];
            let actual_lines: Vec<Vec<u8>> = output.lines.iter().map(|line| line.as_bytes().to_vec()).collect();
            if actual_lines != expected_lines {
                println!("[FAIL] main: lines={} expected={}", actual_lines.len(), expected_lines.len());
                *failures += 1;
            }
            if output.bytes_read != 10 {
                println!("[FAIL] main: bytes_read={} expected={}", output.bytes_read, 10);
                *failures += 1;
            }
            if output.bytes_received != 10 {
                println!("[FAIL] main: bytes_received={} expected={}", output.bytes_received, 10);
                *failures += 1;
            }
            if output.truncated != true {
                println!("[FAIL] main: truncated={} expected={}", output.truncated, true);
                *failures += 1;
            }
            if output.stop_reason.as_str() != "byte_cap" {
                println!("[FAIL] main: stop_reason={} expected={}", output.stop_reason.as_str(), "byte_cap");
                *failures += 1;
            }
            1
        }
        Err(code) => {
            println!("[FAIL] main: получен отказ {code}, ожидался ok");
            *failures += 1;
            1
        }
    }
}

fn case_1(failures: &mut usize) -> usize {
    let input: &[u8] = &[0x61, 0x61, 0x0a];
    let request = Request {
        line_count: 5,
        max_bytes_read: 0,
    };
    match stream(input, &request) {
        Ok(output) => {
            println!("[FAIL] schema-zero-cap: ожидался отказ S1_SCHEMA, получен ok");
            *failures += 1;
            1
        }
        Err(code) => {
            if !code.starts_with("S1_SCHEMA:") {
                println!("[FAIL] schema-zero-cap: code={} expected=S1_SCHEMA", code);
                *failures += 1;
            }
            1
        }
    }
}

fn run_frs_a05(failures: &mut usize) -> usize {
    0
    + case_0(failures)
    + case_1(failures)
}

fn main() {
    let mut failures = 0usize;
    let mut cases = 0usize;
    {
        let before = failures;
        cases += run_frs_a05(&mut failures);
        println!("spec=frs-a05 cases=2 failures={}", failures - before);
    }
    if cases != 2 {
        println!("[FAIL] cases={} expected=2", cases);
        failures += 1;
    }
    println!("total_cases=2 failures={}", failures);
    if failures > 0 { std::process::exit(1); }
}
