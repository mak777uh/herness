# verify: simdjson

README: `README.md`

- строк с числами (широкий счёт): **25**, из них с командой рядом: **1**
- чисел с единицей измерения (строгий счёт): **11**, из них с командой: **0**, доля проверяемых: **0.0**
Квитанция: вход `a4ad9631d2d1f83d…` · инструмент `verify_repo 0.2.0` · 2026-11-15T23:23:26+03:00

Строгий счёт — только строки, где рядом с числом есть единица, которую можно посчитать (тесты, звёзды, загрузки, мс, проценты). Широкий — любая строка с числом. Команда ищется в тексте той же строки и в соседних двух строках.

| строка | число в тексте | команда рядом |
|---|---|---|
| 13 | to parse JSON 4x  faster than RapidJSON and 25x faster than JSON for Modern C++. | **нет** |
| 15 | * **Fast:** Over 4x faster than commonly used production-grade JSON parsers. | **нет** |
| 101 | environments like Visual Studio and Xcode, but different steps are needed. Users of clang++ may need to specify the C++ version (e.g., `c++ -std=c++17`) since clang++ tends to default on C++98. | **нет** |
| 147 | * C++26 reflection example | **нет** |
| 176 | The simdjson library offers high speed whether it processes tiny files (e.g., 300 bytes) | **нет** |
| 182 | For NDJSON files, we can exceed 3 GB/s with our  multithreaded parsing functions. | **нет** |
| 241 | - John Keiser, Daniel Lemire, On-Demand JSON: A Better Way to Parse Documents?, Software: Practice and Experience 54 (6), 2024. | **нет** |
| 245 | - Geoff Langdale, Daniel Lemire, Parsing Gigabytes of JSON per Second, VLDB Journal 28 (6), 2019. | **нет** |
| 249 | - John Keiser, Daniel Lemire, Validating UTF-8 In Less Than One Instruction Per Byte, Software: Practice & Experience 51 (5), 2021. | **нет** |
| 257 | We also had a CppCon 2025 talk. We show how C++26 reflection allows for one-line serialization (to_json(player)) or deserialization—without invasive macros or manual mapping—using nothing but the C++  | **нет** |
| 308 | For efficient number serialization, we bundle Junekey Jeon's implementation of the Dragonbox algorithm for binary to decimal floating-point numbers (https://github.com/jk-jeon/dragonbox). The Dragonbo | **нет** |

## Числа без команды (широкий счёт, первые 20)

- строка 13: to parse JSON 4x  faster than RapidJSON and 25x faster than JSON for Modern C++.
- строка 15: * **Fast:** Over 4x faster than commonly used production-grade JSON parsers.
- строка 16: * **Record Breaking Features:** Minify JSON  at 6 GB/s, validate UTF-8  at 13 GB/s,  NDJSON at 3.5 GB/s.
- строка 18: * **Strict:** Full JSON and UTF-8 validation, lossless parsing. Performance with no compromises.
- строка 99: 0. Prerequisites: `g++` (version 7 or better) or `clang++` (version 6 or better), and a 64-bit
- строка 101: environments like Visual Studio and Xcode, but different steps are needed. Users of clang++ may need to specify the C++ version (e.g., `c++ -std=c++17`) since clang++ tends to default on C++98.
- строка 140: * Compile-Time Parsing presents our compile-time parsing function (C++26 only).
- строка 147: * C++26 reflection example
- строка 158: C++ structs, using C++26 static reflection with GCC 16.2 (-O3). The task is to parse
- строка 162: and Serde. The simdjson library offers full unicode (UTF-8)
- строка 176: The simdjson library offers high speed whether it processes tiny files (e.g., 300 bytes)
- строка 182: For NDJSON files, we can exceed 3 GB/s with our  multithreaded parsing functions.
- строка 241: - John Keiser, Daniel Lemire, On-Demand JSON: A Better Way to Parse Documents?, Software: Practice and Experience 54 (6), 2024.
- строка 243: Some people enjoy reading the first (2019) simdjson paper: A description of the design
- строка 245: - Geoff Langdale, Daniel Lemire, Parsing Gigabytes of JSON per Second, VLDB Journal 28 (6), 2019.
- строка 247: We have an in-depth paper focused on the UTF-8 validation:
- строка 249: - John Keiser, Daniel Lemire, Validating UTF-8 In Less Than One Instruction Per Byte, Software: Practice & Experience 51 (5), 2021.
- строка 253: For the video inclined, we had a talk at QCon San Francisco 2019<br />
- строка 257: We also had a CppCon 2025 talk. We show how C++26 reflection allows for one-line serialization (to_json(player)) or deserialization—without invasive macros or manual mapping—using nothing but the C++ 
- строка 282: RGPIN-2017-03910 and RGPIN-2024-03787.

## Что это не доказывает

- Число без команды не значит «ложь»: оно значит «его нельзя воспроизвести из репозитория».
- Наличие команды не значит, что она проверяет именно это число.
- Отчёт читает только README: `docs/`, `CLAIMS.md`, бенчмарки и CI не разбираются.
- Строгий счёт неполон по устройству: формулировки без единицы в него не попадают.
