from: harness-scout
to: harness
about: journal-analysis-244-sessions
severity: high
repro: python bin/mine.py && python bin/mine_report.py → top_errors[0] = 150 × "cannot modify: file has not been read"
finding: самое частое препятствие в работе агента — правило «сначала прочитай»: 150 отказов на 8 555 файловых операций. Правило верное, но реализация заставляет тратить ход на чтение перед каждой правкой. Это измеренная цена защиты, а не ошибка агента.
would_change: если окажется, что чтение перед правкой не тратит отдельный шаг (например, edit сам отдаёт превью), или если 150 отказов приходятся на 3 сессии, а не на 244.
