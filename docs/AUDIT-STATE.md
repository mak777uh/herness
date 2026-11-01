# Состояние для аудита (снимок 01.11.2026)

утверждений: 214
покрытие: {"total": 214, "closed": 214, "malformed": 0, "coverage": 1.0, "verdict": "CHECKED_ANCHORED", "open": []}
гейтов: 26
отказов записано: 33 (последний F-0034)

## Что проверено исполнением, а не текстом

- приёмка: 24/24 теста, отрицательные контроли на подделку CRC и на ложное «готово»
- Rust: 51 тест, включая опору на имя файла и порог барахтания
- гейт автономии: отрицательный контроль (CITATION.cff → exit 1)
- внешний набор MuSiQue: скачан, схема проверена, 6 задач прогнаны дважды
- метрики: false_completion_rate 0.00 на 22 заявлениях, pass@1 0.56, pass^2 0.61 (C-0212)

## Открытые долги (честно)

- hooks перед вызовом инструмента: не сделаны (идея из claude-code)
- clarify как отдельный шаг: не сделано (идея из Co-OmniSpec)
- 15 из 26 молчаний — зацикливание на одном файле; подсказка о тупике добавлена, эффекта нет (C-0215)
- часть гейтов проверена только успехом, без отрицательного контроля
- внешние обзоры (45 источников) в основном не прочитаны целиком: статусы [А]/[?] в REFS-INDEX

## Где смотреть

| что | файл |
|---|---|
| утверждения | CLAIMS.md |
| что сознательно не утверждаем | NOT-CLAIMED.md |
| отказы и причины | lab/failures/ |
| решения | docs/ADR-*.md, docs/decision-log.md |
| склад литературы | research/REFS-INDEX.md |
| склад данных | research/DATA-LINKS.md |
| склад харнессов | research/HARNESSES-INDEX.md |
| метрики приёмки | research/outputs/acceptance-metrics.txt |
| разбор молчаний | research/outputs/silence-report.txt |
| опыт с отказом | research/outputs/refusal-series.txt |

## Как воспроизвести

```
python bin/hs.py gates          # гейты, включая автономию
python bin/hs.py selftest       # негативные тесты инструмента
python bin/judge_metrics.py     # метрики по журналам
python bin/silence_report.py    # причины молчаний
python bin/check_autonomy.py --paths CITATION.cff   # должен дать exit 1
```
