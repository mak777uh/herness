# Журнал решений владельца

Формат строки: `дата | путь | причина | кто решил`. Гейт `bin/check_autonomy.py --staged` падает,
если защищённый путь попал в индекс без записи здесь.

Защищённые пути перечислены в `lab/autonomy-rules.json`: публикация (`.github/`, `CITATION.cff`,
`docs/PUBLICATION-POLICY.md`), «физика мира» комнаты (`core-rs/configs/`, `core-rs/kernel/`,
`bin/make_initramfs.py`), поверхность моста (`bin/bridge.py`), сами правила автономии.

---

2026-11-01 | lab/autonomy-rules.json | правила автономии заведены как данные по прямому указанию владельца | владелец
2026-11-01 | docs/decision-log.md | журнал решений заведён вместе с правилами | владелец
2026-11-07 | core-rs/kernel/config-6.18.60-hardened2 | владелец поручил закрыть все стены ядра; пересборка с закалкой, стен 24 из 29 | владелец
2026-11-09 | bin/bridge.py | маршрут /v1/net для выхода в сеть из комнаты (ADR-0054): мост передаёт строку net.py, разбор остаётся на хосте; адреса и ключи не покидают хост | агент по поручению владельца (сеть для харнеса)
2026-11-11 | bin/make_initramfs.py | адрес моста кладётся в образ файлом /bridge-host: при restrict=on адрес обязан быть гостевым (10.0.2.15), а переменная окружения до комнаты не доходила — init создавал HttpBridge жёстким 10.0.2.2 (F-0084) | агент по поручению владельца (план, этап 1.3)
2026-11-15 | .github/workflows/gates.yml | CI переписан и включён: четыре job'а (гейты профиль auto, утверждения --fast, selftest, cargo test --lib). Причина: 383 прогона — 383 падения, гейты краснели по конструкции (нет runs/ и core-rs/target в git), а полный verify_claims требует VPN, ключей и Chrome | агент по поручению владельца (фаза 0)
2026-11-15 | docs/decision-log.md | добавлены записи задним числом для путей, изменённых раньше без записи (kernel configs, PUBLICATION-POLICY, gates.yml): долг закрыт явно, а не ослаблением гейта автономии | агент по поручению владельца (фаза 0)
2026-11-16 | docs/decision-log.md | зафиксированы решения владельца Q1–Q10 по R5: пять kind, tool-card-v1 как draft, словарь отказов v2, синтетический fixture первого среза, TCG только симуляция, K6 fail-closed, owner-подпись promotion, search отвергнут, scorecard как draft, сырые ответы оставлены. Подробно — docs/DECISIONS-R5-2026-11-16.md | владелец (чат «давай все как рекомендуешь»)
2026-11-17 | docs/DECISIONS-R8-2026-11-17.md | Q11–Q18/F04/A01 выбраны агентом по прямому делегированию владельца «делай сам все поочерёдно»: policy с `!` и parity, write create-new, legacy read/search/list, KVM_RUN, admission/promoter v0 на test-only ключах, head slice, реестр events и производный active, пилот генератора. Это не approval внешних моделей и не изменение конституции; настоящий owner-ключ не создавался, ни один инструмент не active, K9_proven не выдан | агент по поручению владельца
2026-11-17 | bin/registry_state.py, tests/test_registry_state.py | `active` требует явного `test_only:false`; test-only, отсутствие поля и не-bool дают `admitted_inactive`. Причина: test-only `admitted` с `owner_signed:true` мог стать active. Подпись проверяет promoter; реестр проверяет объявленные поля и остаётся fail-closed | агент по поручению владельца
2026-11-17 | .github/workflows/gates.yml | добавлены проверка пре-регистрации пилота и job `admission` (self-tests, сборка head_slice_host, test-only репетиция); `tests/test_registry_state.py` включён в selftest. Причина: test-only цепочка и guard должны проверяться на чистом LF-клоне, а не только локально | агент по поручению владельца
