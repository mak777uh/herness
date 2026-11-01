# Склад данных: ссылки на наборы (настоящее и будущее)

**Дата:** 01.11.2026. **Правило:** ссылка попадает сюда в день, когда встретилась, даже если сейчас
не нужна. Статус: **[С]** скачан и использован · **[П]** проверено, что доступно · **[?]** не проверял.
Проверка доступности — `python bin/link_check.py` → артефакт `research/outputs/link-check.txt`.

## 1. Уже в работе

| набор | зачем нам | ссылка | лицензия | статус |
|---|---|---|---|---|
| MuSiQue-Ans dev | атрибуция при 20 источниках, support_f1 | huggingface.co/datasets/dgslibisey/MuSiQue/resolve/main/musique_ans_v1.0_dev.jsonl · github.com/StonyBrookNLP/musique | CC BY 4.0 | **[С]** 2417 вопросов, sha256 15fa6379… |

## 2. Тексты, факты, многошаговые вопросы (без сети, файлами)

| набор | зачем | ссылка | статус |
|---|---|---|---|
| HotpotQA | второй профиль атрибуции, supporting facts | hotpotqa.github.io · HF: hotpotqa/hotpot_qa | [?] |
| 2WikiMultiHopQA | сравнение сущностей, противоречия источников | github.com/Alab-NII/2wikimultihop | [?] |
| Natural Questions | короткие фактические ответы | HF: google-research-datasets/natural_questions | [?] |
| SQuAD 2.0 | вопрос + невозможность ответа (у нас нет «честного отказa» задачи) | rajpurkar.github.io/SQuAD-explorer | [?] |
| TriviaQA | длинный хвост фактов | HF: mandarjoshi/trivia_qa | [?] |
| SimpleQA | проверяемые короткие факты, но нужен веб | github.com/openai/simple-evals | [?] |
| GAIA (level 1) | файлы + точный ответ; level 2–3 требуют веба | HF: gaia-benchmark/GAIA | [?] |
| AssistantBench | многосайтовые задачи, ответы test скрыты | HF: AssistantBench/AssistantBench | [?] |
| MemoryAgentBench | память: retrieval, TTL, long-range, **Conflict_Resolution** | HF: ai-hyz/MemoryAgentBench (146 строк) | [?] |
| TRAIL | размеченные трассы с ошибками (span-level) | arxiv.org/abs/2504.13859 | [?] |
| MAST-Data | разметка отказов мультиагентных систем | HF: mcemri/MAST-Data | [?] |

## 3. Код, терминал, состояние среды (нам не в комнату, но для сравнения)

| набор | зачем | ссылка | статус |
|---|---|---|---|
| SWE-bench Verified | эталон строгости приёмки (500 задач) | HF: SWE-bench/SWE-bench_Verified · swebench.com | [?] |
| SWE-bench Lite | быстрые итерации | HF: SWE-bench/SWE-bench_Lite | [?] |
| SWE-bench Pro | устойчив к контаминации | HF: ScaleAI/SWE-bench_Pro · github.com/scaleapi/SWE-bench_Pro-os | [?] |
| Terminal-Bench 2.0 | проверка свойств конечного состояния | github.com/laude-institute/terminal-bench | [?] |
| WebArena | 812 задач, функциональные валидаторы | github.com/web-arena-x/webarena · webarena.dev | [?] |
| WorkArena | корпоративные браузерные задачи, доступ по заявке | github.com/ServiceNow/WorkArena · HF: ServiceNow/WorkArena-Instances | [?] |
| OSWorld | 369 задач, скрипты проверки состояния | github.com/xlang-ai/OSWorld · os-world.github.io | [?] |
| AgentBench | 8 сред, многошаговость | github.com/THUDM/AgentBench | [?] |
| tau2-bench | состояние БД, pass^k, dual-control | github.com/sierra-research/tau2-bench | [?] |
| AppWorld | синтетический мир, программная проверка | github.com/StonyBrookNLP/appworld | [?] |
| TheAgentCompany | чекпоинты, частичный зачёт | github.com/TheAgentCompany/TheAgentCompany | [?] |
| CORE-Bench | воспроизведение статей | github.com/siegelz/core-bench | [?] |
| MLE-bench | 75 Kaggle-соревнований, свои сплиты | github.com/openai/mle-bench | [?] |
| ScienceAgentBench | 102 задачи из 44 публикаций | HF: osunlp/ScienceAgentBench · github.com/OSU-NLP-Group/ScienceAgentBench | [?] |
| PaperBench | репозиторий + reproduce.sh, рубрика | github.com/openai/preparedness (paperbench) | [?] |
| DevAI (Agent-as-a-Judge) | 55 задач, 365 требований | HF: devai-benchmark · github.com/metauto-ai/agent-as-a-judge | [?] |
| miniF2F | формальные доказательства | github.com/openai/miniF2F | [?] |
| AgentDojo | 629 security cases, 97 задач | github.com/ethz-spylab/agentdojo | [?] |
| AgentHarm | 110 вредоносных задач + augmentations | HF: ai-safety-institute/AgentHarm | [?] |
| ToolSandbox | milestones/minefields | github.com/apple/ToolSandbox | [?] |
| BFCL | вызовы функций: AST + execution | gorilla.cs.berkeley.edu/leaderboard.html | [?] |
| AgentBoard | progress rate, подцели | github.com/hkust-nlp/AgentBoard | [?] |

## 4. Метрики и методология (не данные, но нужны вместе с ними)

| источник | что даёт | ссылка |
|---|---|---|
| ABC (rigorous benchmarks) | чеклист валидности, T.1–T.10, R.1–R.13 | arxiv.org/pdf/2507.02825v5 |
| AI Agents That Matter | Парето, стоимость, воспроизводимость | arxiv.org/pdf/2407.01502 |
| tau-bench | формулы pass@k / pass^k | arxiv.org/pdf/2406.12045 |
| Reliability (12 метрик) | consistency, robustness, predictability, safety | arxiv.org/html/2602.16666v3 |
| Survey (2503.16416) | таксономия final/stepwise/trajectory | arxiv.org/pdf/2503.16416 |
| Survey (2507.21504) | «что / как» оценки | arxiv.org/abs/2507.21504 |
| Adding Error Bars to Evals | интервалы, парные сравнения | arxiv.org/abs/2411.00640 |
| Awesome LLM Agent Evaluation | каталог исследований | github.com/vnageshwaran-de/Awesome-LLM-Agent-Evaluation |
| Stanford AIMS | база измерений ИИ | aims.stanford.edu/measurement-db |

## 5. Что брать следующим и почему

1. **SQuAD 2.0 или подобное с «нет ответа»** — у нас нет задачи, где правильный ответ — отказаться.
   Сейчас отказ выглядит как провал, и мы не умеем отличать «честно не смог» от «сломался».
2. **MemoryAgentBench, split Conflict_Resolution** — проверяет перезапись противоречия, а не
   вспоминание; прямо нужно для длинных прогонов.
3. **ToolSandbox** — перенести идею minefields в наш критерий: события, которых быть не должно
   (`must_not_call` — частный случай).

## 6. Оговорки

- Ссылки не гарантируют скачиваемость: WorkArena и ScienceAgentBench требуют заявки или пароля,
  HF-домены из нашего окружения резолвятся нестабильно (C-0198 → потом заработало).
- Лицензии надо проверять перед публикацией производных; сам датасет в git не кладём.
- Ни одна ссылка отсюда не считается «проверенной», пока не помечена **[С]** или **[П]**.
