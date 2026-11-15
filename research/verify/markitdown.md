# verify: markitdown

README: `README.md`

- строк с числами (широкий счёт): **2**, из них с командой рядом: **0**
- чисел с единицей измерения (строгий счёт): **1**, из них с командой: **0**, доля проверяемых: **0.0**
Квитанция: вход `a537c61458d1f73a…` · инструмент `verify_repo 0.2.0` · 2026-11-15T23:12:07+03:00

Строгий счёт — только строки, где рядом с числом есть единица, которую можно посчитать (тесты, звёзды, загрузки, мс, проценты). Широкий — любая строка с числом. Команда ищется в тексте той же строки и в соседних двух строках.

| строка | число в тексте | команда рядом |
|---|---|---|
| 361 | `max_retries` controls the OpenAI client's automatic retries for retryable errors (the default is 2); `5` allows up to six attempts with backoff. See the OpenAI SDK retry documentation. | **нет** |

## Числа без команды (широкий счёт, первые 20)

- строка 38: MarkItDown requires Python 3.10 through 3.14. It is recommended to use a virtual environment to avoid dependency conflicts.
- строка 361: `max_retries` controls the OpenAI client's automatic retries for retryable errors (the default is 2); `5` allows up to six attempts with backoff. See the OpenAI SDK retry documentation.

## Что это не доказывает

- Число без команды не значит «ложь»: оно значит «его нельзя воспроизвести из репозитория».
- Наличие команды не значит, что она проверяет именно это число.
- Отчёт читает только README: `docs/`, `CLAIMS.md`, бенчмарки и CI не разбираются.
- Строгий счёт неполон по устройству: формулировки без единицы в него не попадают.
