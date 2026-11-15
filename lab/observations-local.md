# Наблюдения, свидетельства которых вне git

Это **не утверждения репозитория**: их свидетельства лежат в 
uns/ и 
efs-cache/, а оба каталога
в .gitignore (журналы прогонов и кэш справочника — данные машины, не код). Проверить их из клона
нельзя: команда сработает только там, где эти файлы есть.

Зачем перенесены из CLAIMS.md (15.11.2026). Гейт покрытие считал их закрытыми (closed=303),
потому что проверял только непустоту поля, а живой пересчёт в клоне давал 298: пять артефактов
отсутствуют, шестое (C-0022) считает записи в отсутствующем кэше. Получалось число «покрытие 1.00»,
которое держалось на файлах, существующих только у автора. Это тот же класс, что F-0088/F-0089:
прибор, который льстит себе. Anchored-покрытие должно означать «проверяемо из репозитория», поэтому
машинно-локальные наблюдения вынесены сюда, а не помечены «закрытыми».

**Как вернуть в CLAIMS.md:** положить свидетельство в evidence/objects/ (там файлы лежат
байт-в-байт и адресуются дайджестом), указать путь evidence/objects/<sha256> в колонке «артефакт»
и перегенерировать 
esearch/claims-coverage.json. Формулировка при этом не меняется — меняется
только то, что свидетельство становится воспроизводимым из клона.

| id | наблюдение | тип | команда | свидетельство (вне git) | дата | ожидание |
|---|---|---|---|---|---|---|
| C-0005 | IronClaw (nearai) применяет инъекцию ключей на границе хоста, allowlist эндпоинтов и скан утечек | observation | `python bin/check_artifacts.py C-0005` | refs-cache/nearai/ironclaw/README.md | 29.10.2026 | `host boundary` |
| C-0012 | Запуск dsh headless из CLI без креденшелов падает MISSING_CREDENTIAL; DEEPSEEK_API_KEY из ~/.dsh/.credentials.yaml невалиден (HTTP 401) | observation | `python -c "import pathlib;logs=list(pathlib.Path('runs').glob('*/stderr.log'));hit=any('MISSING_CREDENTIAL' in f.read_text(errors='replace') for f in logs);print('MISSING_CREDENTIAL' if hit else 'not found');raise SystemExit(0 if hit else 1)"` | runs/*/stderr.log | 29.10.2026 (обновлено) | `MISSING_CREDENTIAL` |
| C-0022 | В кэше справочника 30 каталогов репозиториев с документами (было 29 на 08.11; выросло на 1: chaitin/MonkeyCode — разбор в research/ADOPTION-monkeycode.md) | statistics | `python bin/count.py repos` | research/outputs/repos-count.txt | 08.11.2026 | `repos=30` |
| C-0030 | glm-5.3-flash нестабилен: два прогона подряд оборвались (RemoteDisconnected), третий прошёл за 2,8 с — это нестабильность соединения, а не отказ модели | observation | `python bin/check_artifacts.py C-0030` | runs/glm-failure.log | 29.10.2026 | `done` |
| C-0033 | Живые прогоны по классам: T-0001 (4 шага, ответ 0 — верно), T-0003 (3 шага, файл создан), T-0004 (2 шага, 5/5), T-0005 (1 шаг, отказ без инструментов), T-0006 (3 шага после list_dir: 60 прогонов, 35 live), T-0007 (1 шаг, честное «нет данных») | test | `python bin/check_artifacts.py C-0033` | runs/step-measure.json | 29.10.2026 | `T-0006` |
| C-0036 | Замер шагов по классам: T-0001 4, T-0002 4, T-0003 3, T-0004 2, T-0006 4, T-0007 1; пороги в profiles.json = замер + 2 | statistics | `python bin/check_artifacts.py C-0036` | runs/step-measure.json | 29.10.2026 | `T-0001` |

## Почему каждое здесь

| id | почему не в git |
|---|---|
| C-0005 | 
efs-cache/ — кэш справочника, воспроизводится hs refs sync (нужна сеть) |
| C-0012 | 
uns/ — журналы прогонов машины автора |
| C-0022 | 
esearch/outputs/repos-count.txt считается по 
efs-cache/, которого в клоне нет |
| C-0030 | 
uns/glm-failure.log — лог провайдера на машине автора |
| C-0033 | 
uns/step-measure.json — замер шагов на машине автора |
| C-0036 | 
uns/step-measure.json — тот же замер, пороги profiles.json |
