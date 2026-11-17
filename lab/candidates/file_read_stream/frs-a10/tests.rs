include!("source.rs");

fn case_0(failures: &mut usize) -> usize {
    let input: &[u8] = &[0x68, 0xc3, 0xa9, 0x6c, 0x6c, 0x6f, 0x0a];
    let request = Request {
        line_count: 2,
        max_bytes_read: 100,
    };
    match stream(input, &request) {
        Ok(output) => {
            let expected_lines: Vec<Vec<u8>> = vec![vec![0x68, 0xc3, 0xa9, 0x6c, 0x6c, 0x6f]];
            let actual_lines: Vec<Vec<u8>> = output.lines.iter().map(|line| line.as_bytes().to_vec()).collect();
            if actual_lines != expected_lines {
                println!("[FAIL] main: lines={} expected={}", actual_lines.len(), expected_lines.len());
                *failures += 1;
            }
            if output.bytes_read != 7 {
                println!("[FAIL] main: bytes_read={} expected={}", output.bytes_read, 7);
                *failures += 1;
            }
            if output.bytes_received != 7 {
                println!("[FAIL] main: bytes_received={} expected={}", output.bytes_received, 7);
                *failures += 1;
            }
            if output.truncated != false {
                println!("[FAIL] main: truncated={} expected={}", output.truncated, false);
                *failures += 1;
            }
            if output.stop_reason.as_str() != "eof" {
                println!("[FAIL] main: stop_reason={} expected={}", output.stop_reason.as_str(), "eof");
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

fn run_frs_a10(failures: &mut usize) -> usize {
    0
    + case_0(failures)
}

fn main() {
    let mut failures = 0usize;
    let mut cases = 0usize;
    {
        let before = failures;
        cases += run_frs_a10(&mut failures);
        println!("spec=frs-a10 cases=1 failures={}", failures - before);
    }
    if cases != 1 {
        println!("[FAIL] cases={} expected=1", cases);
        failures += 1;
    }
    println!("total_cases=1 failures={}", failures);
    if failures > 0 { std::process::exit(1); }
}
