# ADR-0061: namespace моделей Lean (F-0080) — агрегат Proofs собирается

- **Статус:** принято (15.11.2026)
- **Смежное:** F-0080 (false-green: поодиночке зелёно, вместе красно), N4 (резолвер путей), ADR-0060
- **Контекст:** `Proofs/Policy.lean` и `Proofs/PartBridge.lean` независимо объявляли в корне
  `Effect`, `Rule`, `hasAllow`, `hasDeny`. Корневой `Proofs.lean` импортирует оба, поэтому
  `lake build Proofs` падал: «environment already contains 'Effect.rec' from Proofs.Policy».
  Каждый модуль поодиночке собирался зелёным, приборы (`lean_check`, `bridge_parts`) собирали
  только свои модули — конфликт не проявлялся. Это false-green: зелёный по частям ≠ зелёный вместе.

## Решение

Обернуть каждый модуль в собственное пространство имён: `namespace Policy … end Policy` и
`namespace PartBridge … end PartBridge`. Все объявления становятся `Policy.*` / `PartBridge.*`
(`Policy.Effect`, `PartBridge.Effect`, `Policy.Rule`, `PartBridge.Rule`, `Policy.hasAllow`,
`PartBridge.hasDeny` и т.д.). Коллизия исчезает: полные имена различны.

- `abbrev Policy` внутри `namespace Policy` переименован в `Rules` (`Policy.Rules := List Rule`),
  чтобы не плодить `Policy.Policy` и освободить читаемое имя. Ссылки `(p : Policy)` → `(p : Rules)`.
- Теоремы сохраняются, но получают префикс модуля: `Policy.deny_beats_allow`,
  `PartBridge.no_bridge_of_incompatible` и т.д. Это **смена контракта имён** (см. ниже).
- `Bridge.lean` не коллидирует (объявляет `Config`/`Request`/…), обёртка не требуется, но для
  единообразия агрегата остаётся как есть (его имена и так уникальны).

## Почему namespace, а не переименование

Переименование (`PartEffect`/`PartRule`) развело бы имена, но оставило бы модели в общем корне и
не выражало бы принадлежность объявления модулю. Namespace делает контракт явным: `Policy.Effect`
и `PartBridge.Effect` — разные типы с разной семантикой (allow/deny против allow/deny/duty), и это
видно из имени. Карта F-0080 предлагала именно namespace.

## Каскад ссылок (смена контракта имён)

- `proofs/Probe.lean`: `#print axioms Policy.<теорема>` (6 имён).
- `bin/lean_check.py`, `bin/lean_wsl.py`: список `THEOREMS` получает префикс `Policy.`.
- `proofs/Proofs/Negative.lean`: `open Policy` (использует `policyAllows`, `deny_beats_allow`, …).
- `proofs/Proofs/PartBridgeNegative.lean`: `open PartBridge` (использует `Effect.deny/duty`, `Bridge`, …).
- Отрицательные контроли обязаны по-прежнему ПАДАТЬ (`unsolved goals`): `Proofs.Negative`,
  `Proofs.PartBridgeNegative`. Если NC собирается — проверка пуста, доказательствам верить нельзя.

## Проверка (RED → GREEN)

- **RED-before:** `lake build Proofs` (WSL rc2) → rc=1, «environment already contains 'Effect.rec'
  from Proofs.Policy» (журнал `research/outputs/lean-wsl-check.txt`, коммит 91c47c1).
- **GREEN-after:** `lake build Proofs` → rc=0; контуры `Proofs.Policy` и `Proofs.PartBridge` зелёные;
  аксиомы теорем только стандартные (`propext`, `Classical.choice`, `Quot.sound`); оба NC отвергнуты.
  Исполнитель: `bin/lean_wsl.py` (WSL Ubuntu, toolchain rc2 из `proofs/lean-toolchain`).

## Что это НЕ доказывает

- Что модели соответствуют Rust-коду: доказывается свойство модели, соответствие проверяется
  сверкой (`policy_diff`, `PartBridgeDiff`) и тестами, не этой сборкой.
- Что Lean вызывается в CI: исполнитель host-only (WSL), CI — ubuntu-latest без WSL/Lean;
  сборка в CI требует установки Lean rc2 (отдельный шаг).
- Что прибор ловит произвольную коллизию: он ловит регрессию сборки агрегата; новые коллизии
  имён видны только при сборке корневого `Proofs.lean`, а не отдельных модулей.