# verify: LightGBM

README: `README.md`

- строк с числами (широкий счёт): **3**, из них с командой рядом: **0**
- чисел с единицей измерения (строгий счёт): **3**, из них с командой: **0**, доля проверяемых: **0.0**
Квитанция: вход `799982daa89a30b8…` · инструмент `verify_repo 0.2.0` · 2026-11-15T23:23:27+03:00

Строгий счёт — только строки, где рядом с числом есть единица, которую можно посчитать (тесты, звёзды, загрузки, мс, проценты). Широкий — любая строка с числом. Команда ищется в тексте той же строки и в соседних двух строках.

| строка | число в тексте | команда рядом |
|---|---|---|
| 183 | Yu Shi, Guolin Ke, Zhuoming Chen, Shuxin Zheng, Tie-Yan Liu. "Quantized Training of Gradient Boosting Decision Trees" (link). Advances in Neural Information Processing Systems 35 (NeurIPS 2022), pp. 1 | **нет** |
| 185 | Guolin Ke, Qi Meng, Thomas Finley, Taifeng Wang, Wei Chen, Weidong Ma, Qiwei Ye, Tie-Yan Liu. "LightGBM: A Highly Efficient Gradient Boosting Decision Tree". Advances in Neural Information Processing  | **нет** |
| 187 | Qi Meng, Guolin Ke, Taifeng Wang, Wei Chen, Qiwei Ye, Zhi-Ming Ma, Tie-Yan Liu. "A Communication-Efficient Parallel Algorithm for Decision Tree". Advances in Neural Information Processing Systems 29 ( | **нет** |

## Числа без команды (широкий счёт, первые 20)

- строка 183: Yu Shi, Guolin Ke, Zhuoming Chen, Shuxin Zheng, Tie-Yan Liu. "Quantized Training of Gradient Boosting Decision Trees" (link). Advances in Neural Information Processing Systems 35 (NeurIPS 2022), pp. 1
- строка 185: Guolin Ke, Qi Meng, Thomas Finley, Taifeng Wang, Wei Chen, Weidong Ma, Qiwei Ye, Tie-Yan Liu. "LightGBM: A Highly Efficient Gradient Boosting Decision Tree". Advances in Neural Information Processing 
- строка 187: Qi Meng, Guolin Ke, Taifeng Wang, Wei Chen, Qiwei Ye, Zhi-Ming Ma, Tie-Yan Liu. "A Communication-Efficient Parallel Algorithm for Decision Tree". Advances in Neural Information Processing Systems 29 (

## Что это не доказывает

- Число без команды не значит «ложь»: оно значит «его нельзя воспроизвести из репозитория».
- Наличие команды не значит, что она проверяет именно это число.
- Отчёт читает только README: `docs/`, `CLAIMS.md`, бенчмарки и CI не разбираются.
- Строгий счёт неполон по устройству: формулировки без единицы в него не попадают.
