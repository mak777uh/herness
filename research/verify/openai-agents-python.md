# verify: openai-agents-python

README: `README.md`

- строк с числами (широкий счёт): **3**, из них с командой рядом: **0**
- чисел с единицей измерения (строгий счёт): **1**, из них с командой: **0**, доля проверяемых: **0.0**
Квитанция: вход `cf68cb43182d6ea4…` · инструмент `verify_repo 0.2.0` · 2026-11-15T23:12:11+03:00

Строгий счёт — только строки, где рядом с числом есть единица, которую можно посчитать (тесты, звёзды, загрузки, мс, проценты). Широкий — любая строка с числом. Команда ищется в тексте той же строки и в соседних двух строках.

| строка | число в тексте | команда рядом |
|---|---|---|
| 3 | The OpenAI Agents SDK is a lightweight yet powerful framework for building multi-agent workflows. It is provider-agnostic, supporting the OpenAI Responses and Chat Completions APIs, as well as 100+ ot | **нет** |

## Числа без команды (широкий счёт, первые 20)

- строка 3: The OpenAI Agents SDK is a lightweight yet powerful framework for building multi-agent workflows. It is provider-agnostic, supporting the OpenAI Responses and Chat Completions APIs, as well as 100+ ot
- строка 14: 1. **Realtime agents**: Build powerful voice agents with `gpt-realtime-2.1` and full agent features
- строка 27: To get started, set up your Python environment (Python 3.10 or newer required), and then install OpenAI Agents SDK package.

## Что это не доказывает

- Число без команды не значит «ложь»: оно значит «его нельзя воспроизвести из репозитория».
- Наличие команды не значит, что она проверяет именно это число.
- Отчёт читает только README: `docs/`, `CLAIMS.md`, бенчмарки и CI не разбираются.
- Строгий счёт неполон по устройству: формулировки без единицы в него не попадают.
