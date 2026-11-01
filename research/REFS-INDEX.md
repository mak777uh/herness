# Индекс литературы и данных: склад на будущее

**Дата:** 01.11.2026. **Зачем:** ничего не терять. Сюда складывается всё, что может понадобиться
позже, с пометкой, **что именно я читал**, а что взято из обзоров/абстрактов. Числа из вторичных
источников в `CLAIMS.md` не идут — только после сверки (`bin/fetch_url.py` + дайджест).

Статусы: **[П]** прочитан полный текст · **[А]** абстракт/таблица из обзора · **[?]** не открывал.

## 1. Методология оценки (самое важное для нас)

| работа | что даёт | ссылка | статус |
|---|---|---|---|
| Survey on Evaluation of LLM-based Agents | таксономия: final-response / stepwise / trajectory, reference-based vs reference-free | arxiv.org/pdf/2503.16416 | [А] |
| Evaluation and Benchmarking of LLM Agents: A Survey (KDD'25) | двумерная таксономия «что / как» | arxiv.org/abs/2507.21504 | [А] |
| Establishing Best Practices for Rigorous Agentic Benchmarks (ABC) | **outcome validity vs task validity**, чеклист T.1–T.10, R.1–R.13 | arxiv.org/pdf/2507.02825v5 | [А] |
| AI Agents That Matter | Парето точность/цена, контроль стоимости, дефекты воспроизводимости | arxiv.org/pdf/2407.01502 | [А] |
| Towards a Science of AI Agent Reliability | 12 метрик: consistency, robustness, predictability, safety | arxiv.org/html/2602.16666v3 | [А] |
| Adding Error Bars to Evals | парные различия, доверительные интервалы | arxiv.org/abs/2411.00640 | [?] |
| Preregistration for Experiments with AI Agents | пре-регистрация для агентных экспериментов | arxiv.org/html/2606.11217v1 | [А] |
| Mitigating LLM-based p-Hacking (next-LLM) | 73,9 % / 72,7 % блокировки переноса p-hack | arxiv.org/html/2606.27687v1 | [А] |
| Position: Agent Evaluation Should Be Agentified (ICML'26) | отделить исполнителя от оценщика, общий интерфейс | proceedings.mlr.press/v306/liu26gy.html | [А] |

## 2. Проверяемые бенчмарки (execution / state)

| бенчмарк | что проверяет | текст | данные | статус |
|---|---|---|---|---|
| SWE-bench / Verified | FAIL_TO_PASS + PASS_TO_PASS | arxiv.org/abs/2310.06770 | HF: SWE-bench/SWE-bench_Verified (500) | [А] |
| SWE-Bench Pro | устойчив к контаминации, ≤23,3 % у лучших | arxiv.org/abs/2509.16941 | HF: ScaleAI/SWE-bench_Pro | [А] |
| WebArena | 812 задач, функциональные валидаторы состояния | arxiv.org/abs/2307.13854 | webarena.dev, github.com/web-arena-x/webarena | [А] |
| OSWorld | 369 задач, свои скрипты проверки; люди 72,36 %, лучшая модель 12,24 % | arxiv.org/abs/2404.07972 | os-world.github.io | [А] |
| Terminal-Bench 2.0 | тесты свойств конечного состояния контейнера | arxiv.org/abs/2601.11868 | github.com/laude-institute/terminal-bench | [А] |
| tau-bench | состояние БД против эталона; **pass^k**; 61 % → 25 % | arxiv.org/pdf/2406.12045 | github.com/sierra-research/tau2-bench | [А] |
| GAIA | 466 вопросов, quasi exact match; трейс не оценивается | arxiv.org/pdf/2311.12983 | HF: gaia-benchmark/GAIA | [А] |
| AgentBench | 8 сред, многошаговые сценарии | arxiv.org/abs/2308.03688 | github.com/THUDM/AgentBench | [А] |
| AssistantBench | 214 задач по 258 сайтам; test answers скрыты | arxiv.org/abs/2407.15711 | HF: AssistantBench/AssistantBench | [А] |
| MLE-bench | 75 Kaggle-соревнований, свои сплиты | — | github.com/openai/mle-bench | [А] |
| ScienceAgentBench | 102 задачи из 44 публикаций, 9 экспертов | arxiv.org/abs/2410.05080 | HF: osunlp/ScienceAgentBench | [А] |
| PaperBench | репозиторий + `reproduce.sh`; Code / Execution / Result Match | arxiv.org/pdf/2504.01848 | — | [А] |
| CORE-Bench | воспроизведение результатов статей | arxiv.org/abs/2409.11363 | github.com/siegelz/core-bench | [А] |
| TheAgentCompany | чекпоинты, частичный зачёт | arxiv.org/abs/2412.14161 | github.com/TheAgentCompany/TheAgentCompany | [А] |
| BrowseComp | короткий ответ + LLM-грейдер | arxiv.org/abs/2504.12516 | github.com/openai/simple-evals | [А] |
| miniF2F | 244 test + 244 valid, машинно-проверяемое доказательство | arxiv.org/html/2109.00110v2 | github.com/openai/miniF2F | [А] |
| MuSiQue | 20 абзацев, 2–4 поддерживающих, support_f1 | arxiv.org/pdf/2108.00573 | HF: dgslibisey/MuSiQue (dev 2417) | **[П]** |

## 3. Процесс, память, инструменты

| работа | что даёт | ссылка | статус |
|---|---|---|---|
| BFCL | AST-substring + execution matching, state/response для multi-turn | mlresearch/v267/patil25a | [А] |
| AgentBoard | progress rate, subgoals, grounding accuracy | arxiv.org/pdf/2401.13178 | [А] |
| ToolSandbox | **milestones + minefields**, нарушение minefield обнуляет траекторию | arxiv.org/pdf/2408.04682 | [А] |
| MemoryAgentBench | retrieval, test-time learning, long-range, selective forgetting; HF 146 строк, splits включая Conflict_Resolution | arxiv.org/pdf/2507.05257 | [А] |
| TRAIL | 148 размеченных трасс, 841 span-level ошибка | arxiv.org/abs/2504.13859 | [А] |
| MAST | таксономия отказов мультиагентных систем, 1600+ трасс | arxiv.org/abs/2503.13657 | [А] |
| Agent GPA | выравнивание цель → план → действие | arxiv.org/abs/2510.08847 | [А] |

## 4. Судьи, безопасность, устойчивость

| работа | что даёт | ссылка | статус |
|---|---|---|---|
| MT-Bench / LLM-as-a-Judge | position, verbosity, self-enhancement bias; >80 % согласия | arxiv.org/abs/2306.05685 | [А] |
| Judging the Judges | 15 судей, 150k сравнений, position bias не случаен | arxiv.org/abs/2406.07791 | [А] |
| Agent-as-a-Judge / DevAI | 55 задач, 365 требований; 90 % против 70 % у LLM-судьи | arxiv.org/pdf/2410.10934 | [А] |
| AgentDojo | 97 задач, 629 security cases; benign utility / under attack / ASR | NeurIPS 2024 D&B | [А] |
| AgentHarm | 110 вредоносных задач, harm score по рубрике, не «мнение LLM» | arxiv.org/abs/2410.09024 | [А] |
| A Survey of Agentic Benchmarks (безопасность) | 40+ behavioral safety benchmarks, таксономия | arxiv.org/html/2605.16282v1 | [А] |
| Towards a Science of Scaling Agent Systems | 260 конфигураций, +80,8 % / −70 %; потолок 45 %; ошибки ×17,2 против ×4,4 | arxiv.org/pdf/2512.08296 | [А] |
| Reflexion | вербальная рефлексия вместо обновления весов | arxiv.org/pdf/2303.11366 | [А] |
| ReAct | чередование reasoning/acting; Ablations Standard/CoT/Act | arxiv.org/pdf/2210.03629 | [П, ранее] |
| Agentless | 32,00 % на SWE-bench Lite за $0.70 — сильный неавтономный baseline | arxiv.org/abs/2407.01489 | [А] |

## 5. Ложный успех и подделка свидетельств

| работа | число | статус |
|---|---|---|
| From Confident Closing to Silent Failure | 45–48 % провалов в single-control, 3 % dual-control, 75,8 % AppWorld | [А] |
| Failure-Transparent Agents | 22,8 % → 9,3 % → 0,8 % (контракт свидетельств) | [А] |
| OverclaimBench | 67,9 % не прочитали все файлы; 80,4 % вводили в заблуждение | [А] |
| LLM Agents Can Tamper With Their Own Traces | 70–90 % удаления трассировки, все харнессы кроме Muse Code | [А] |
| How Benchmarks Mis-Score Computer-Use Agents | 15,3 % записанных FAIL неверны | [А] |
| Why OpenAI no longer evaluates SWE-bench Verified | 59,4 % проверенных задач имеют дефектные тесты | [А] |

## 6. Метрики, которые надо завести у нас

```
false_completion_rate = |{claim=done ∧ verdict≠accept}| / |{claim=done}|
completion_precision  = |{claim=done ∧ verdict=accept}| / |{claim=done}|
completion_recall     = |{accept ∧ claim=done}| / |{accept}|
pass^k                = mean_i C(c_i,k)/C(n_i,k)   (успех ВСЕХ k прогонов)
pass@k                = mean_i [1 − C(n_i−c_i,k)/C(n_i,k)]
cost_per_verified     = расходы / |{accept}|      (неудачи в знаменателе затрат)
unknown_share         = |{unverified}| / |{все прогоны}|
```

Считать по журналам `runs/accept/*.bin`. Данные есть, кода нет — это ближайшая работа.

## 7. Что брать в первую очередь (приоритет чтения целиком)

1. **ABC / rigorous benchmarks** — чеклист валидности: наши F-0028…F-0032 это ровно его случаи.
2. **tau-bench** — формулы pass^k и почему общая средняя вероятность не заменяет среднее по задачам.
3. **ToolSandbox** — milestones/minefields как обобщение `require_events` + `must_not_call`.
4. **MemoryAgentBench** — split `Conflict_Resolution`: проверка «перезаписать противоречие», а не
   «вспомнить факт».
5. **AgentDojo** — разделение «польза без атаки / польза под атакой / успех атаки».

## 8. Правила склада

- Новый источник добавляется сюда **в день, когда встретился**, даже если не нужен сейчас.
- Каждая строка имеет статус; «[А]» нельзя цитировать как «[П]».
- Числа из «[А]» попадают в `CLAIMS.md` только после сверки и только как `observation`.
- Ссылки не переписываются вручную: скачивание через `bin/fetch_url.py`, sha256 в артефакте.

## 9. Добавлено после разбора P30 (01.11.2026)

Статус **[А]** у всех: числа взяты из ответов моделей (фрагменты статей), полные тексты не читались.
Ссылки — arXiv; перед использованием в плане читать целиком.

| работа | что измеряет | ссылка |
|---|---|---|
| DeLoop: Repeated Actions as Self-Supervision | петля = тот же вызов + тот же результат; loop rate 57,3 %→6,1 %, шаги 15,00→4,67, токены −47 %; полезные повторы 29,9 %→69,8 % | arxiv.org/html/2610.19376 |
| When Agents Do Not Stop | статический поиск бесконечных циклов, 6 549 репозиториев, precision 91,9 % | arxiv.org/abs/2607.01641 |
| AgentQuest | progress rate и repetition rate; Mastermind SR 47 %→60 % после памяти о догадках; в LTP повторы полезны (RR 81 %) | aclanthology.org/2024.naacl-demo.19.pdf |
| More with Less (turn control) | лимит 75-го перцентиля: стоимость −23…−68 %, solve −5…−8 п.п.; без напоминания обвал; Dynamic X→Y лучше | arxiv.org/html/2510.16786v2 |
| Budget-Aware Tool Use (BATS) | Budget Tracker: 55,4 % против 36,8 % при равной цене, 500 задач SWE-bench Verified | arxiv.org/pdf/2511.17006 |
| SWE-agent | ACI против shell-only: 18 % против 11 % на SWE-bench Lite; абляции интерфейса | arxiv.org/pdf/2405.15793 |
| Is Bash All You Need? | Bash против typed tools: +24,6 п.п. (TheAgentCompany, n=348), +6,2 п.п. (APEX, n=960); reward hacking в shell-режимах | arxiv.org/html/2609.11999v1 |
| Darwin Gödel Machine | SWE-bench 20 %→50 %, Polyglot 14,2 %→30,7 %; без открытого поиска 23 %; objective hacking (узел 114) | arxiv.org/pdf/2505.22954 |
| A Self-Improving Coding Agent (SICA) | правки собственного кода: 17 %→51–53 % на 50 задачах; $7k за 15 итераций | arxiv.org/html/2504.15228v2 |
| SpecBench | reward hacking как gap validation/held-out; 97 %/0 % на C-compiler; +27 п.п. на 10× LOC | arxiv.org/pdf/2605.21384v1 |
| AgentAbstain | paired act/abstain, 263 пары, лучший 59,5 %; implicit abstention 17,8 %, post-hoc 2,6 % | arxiv.org/pdf/2607.10059 |
| Agentic Abstention | Abstention Recall@K, 89 solvable / 188 unsolvable; over-abstention 0–8 % | arxiv.org/html/2606.28733 |
| Failure-Transparent Agents | ложный успех 22,8 %→9,3 %→0,8 %; контракт STATUS/EVIDENCE/LIMITATION/NEXT ACTION | arxiv.org/html/2609.35732v1 |
| EvoAgentBench | перенос между доменами; Memento −36,3 п.п. в одной ячейке; 528 train / 267 test | arxiv.org/html/2607.05202v1 |
| WebRollback | явный откат: full success 38,5 %→43,5 % на 100 задачах | aclanthology.org/2026.eacl-short.12.pdf |
| Semantic Early-Stopping | судья-независимый стопор: −38 % токенов при том же качестве; полный каскад дороже baseline на 129 % | arxiv.org/pdf/2606.27009 |
| Same Task, Different Work | «сравни несколько подходов»: reasoning ×2,4–7,4 без выигрыша в success | arxiv.org/html/2608.01347v3 |
| SandboxEscapeBench | побеги из контейнеров: 803 прогона, 9 моделей, 18 уязвимых конфигураций; Opus 0,49 | arxiv.org/html/2603.02277v2 |
| Sandlock | Landlock+seccomp: ~5 мс на запуск против Docker (≈44× медленнее) | arxiv.org/html/2605.26298 |
| Firecracker / gVisor study | boot <125 мс, ≤5 МБ на микро-VM; число разрешённых syscall 36 / 53–68 / все кроме 44 | usenix.org/system/files/nsdi20-paper-agache.pdf |
| METR Time Horizons | нормировка сложности через человеческое время; >16 ч ненадёжно | metr.org/time-horizons |

### Что с этим делать

- в план идут только те, у кого есть **наше** подтверждение или измеренный риск (A-0010…A-0014);
- остальные лежат как ориентир: при следующей проблеме — `python bin/shelf.py search "<проблема>"`.
