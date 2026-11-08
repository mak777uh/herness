# Приёмка прогона: цикл в комнате → журнал выносится на диск → проверка на хосте.
#
# Зачем отдельный скрипт: run.ps1 проверяет то, что цикл напечатал сам. Здесь проверяется другое —
# что критерий, объявленный ДО прогона и лежащий вне комнаты, действительно исполняется над байтами
# журнала, а не над рассказом модели (ADR-0049).
#
# Порядок шагов намеренно скучный:
#   1. собрать образ комнаты с нужным режимом;
#   2. загрузить его с диском, дать циклу отработать;
#   3. смонтировать диск на хосте (WSL) и скопировать hs-journal.bin;
#   4. прогнать bin/accept.py с критерием из accept/ и вернуть его код.
param(
    [string]$Mode = "loop",
    [string]$Criteria = "accept/room-claims-statistics.json",
    [string]$Image = "core-rs\acc.img",
    [string]$Kernel = "vmlinuz-own-rng",
    [string]$Accel = "whpx",
    [int]$Memory = 512,
    [int]$TimeoutSec = 30,
    # Задача выдаётся комнате файлом; критерий при этом остаётся на хосте.
    [string]$Task = "",
    # Сеть нужна, чтобы цикл мог позвать модель через мост на хосте (10.0.2.2:8790).
    [switch]$Net,
    # Объявить прогон хостовым: события должны подтверждаться хостом (H-0007).
    [switch]$HostRun
)
$ErrorActionPreference = "Stop"
$root = "C:\111\herness"
$core = Join-Path $root "core-rs"
$boot = Join-Path $core "boot"
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
$runs = Join-Path $root "runs\accept"
New-Item -ItemType Directory -Force -Path $runs | Out-Null

# Комната — часть прибора: если образ отстал от репозитория, задача становится невыполнимой,
# а выглядит это как провал модели (F-0035). Поэтому прогон начинается с проверки образа.
$room = Join-Path $root "lab\room.json"
if ((Test-Path $room) -and $Mode -ne "none") {
    Push-Location $root
    python bin\build_room.py --check | Out-Null
    $roomCode = $LASTEXITCODE
    Pop-Location
    if ($roomCode -ne 0) {
        Write-Host "итог: FAIL (комната не совпадает с манифестом — прогон не начат)"
        python bin\build_room.py --check | Select-Object -Last 6
        exit 3
    }
}

$env:HS_MODE = $Mode
# Хостовый прогон: события должны подтверждаться хостом, иначе done не выдаётся (H-0007).
if ($HostRun) { $env:HS_HOST_RUN = "accept-" + (Get-Date -Format "yyyyMMdd-HHmmss") } else { Remove-Item Env:\HS_HOST_RUN -ErrorAction SilentlyContinue }
# Связка: если критерий требует хостовый журнал, комната обязана слать события. Иначе граница
# держалась бы на том, что запускающий не забыл флаг — то есть на дисциплине, а не на контракте.
$hostRunFromCriteria = $null
# Бюджет прогона берётся из самого критерия: если критерий разрешает 12 шагов, а комната даёт 8,
# приёмка невыполнима по построению — не потому, что модель не справилась (F-0026).
$criteriaPath = if (Test-Path $Criteria) { $Criteria } else { Join-Path $root $Criteria }
if (Test-Path $criteriaPath) {
    $spec = Get-Content $criteriaPath -Raw | ConvertFrom-Json
    $budget = [ordered]@{}
    if ($null -ne $spec.max_steps) { $budget.steps = [int]$spec.max_steps }
    if ($null -ne $spec.max_allowance) { $budget.allowance = [double]$spec.max_allowance }
    # Секунды берутся из параметра прогона: жёсткие 240 с обрывали длинные задачи и выглядели
# как «шаги кончились» (F-0045).
$budget.seconds = [int]$TimeoutSec
    $env:HS_BUDGET = ($budget | ConvertTo-Json -Compress)
    if ($spec.host_run) { $env:HS_HOST_RUN = [string]$spec.host_run }
    # Рамки задачи: read-only файл в комнате, объявлен критерием (H-0010).
    if ($null -ne $spec.scope) { $env:HS_SCOPE = ($spec.scope | ConvertTo-Json -Compress) } else { Remove-Item Env:\HS_SCOPE -ErrorAction SilentlyContinue }
    # Выдача инструментов: объявлена в критерии, значит комната получает ровно её, а не весь набор.
    if ($null -ne $spec.tools) {
        $env:HS_TOOLS = ($spec.tools | ConvertTo-Json -Compress)
    } else {
        Remove-Item Env:\HS_TOOLS -ErrorAction SilentlyContinue
    }
} else { Remove-Item Env:\HS_BUDGET -ErrorAction SilentlyContinue; Remove-Item Env:\HS_TOOLS -ErrorAction SilentlyContinue }
if ($Task) { $env:HS_TASK = $Task } else { Remove-Item Env:\HS_TASK -ErrorAction SilentlyContinue }
if ($Net) {
    # Токен моста и имя модели — не секрет провайдера: ключ остаётся на хосте (ADR-0046).
    $env:HS_BRIDGE_TOKEN = (Get-Content "C:\111\env\bridge-token.txt" -Raw).Trim()
    $env:HS_BRIDGE_MODEL = "deepseek-v4.1-flash"
}
python (Join-Path $root "bin\make_initramfs.py") | Out-Null
if ($LASTEXITCODE -ne 0) { throw "упаковка initramfs не прошла" }

$out = Join-Path $boot "accept-run.txt"
$err = Join-Path $boot "accept-run.err"
Remove-Item $out, $err -ErrorAction SilentlyContinue

$args = @('-m', "$Memory", '-smp', '1',
          '-kernel', (Join-Path $boot $Kernel),
          '-initrd', (Join-Path $boot 'initramfs.cpio.gz'),
          '-device', 'virtio-rng-pci',
          '-drive', "file=$((Resolve-Path (Join-Path $root $Image)).Path),format=raw,if=virtio",
          '-append', '"console=ttyS0 panic=-1 ip=dhcp"',
          '-nographic', '-no-reboot')
if ($Net) { $args = @('-netdev', 'user,id=n0', '-device', 'virtio-net-pci,netdev=n0') + $args }
if ($Accel -ne "none") { $args = @('-accel', $Accel) + $args }
$process = Start-Process -FilePath $qemu -ArgumentList $args -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$text = ""
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 150
    $text = (Get-Content $out -Raw -ErrorAction SilentlyContinue) -as [string]
    if ($text -and $text.Contains("система жива")) { break }
    if ($process.HasExited) { break }
}
if (-not $process.HasExited) { $process.Kill() }

$lines = ($text -split "`n") | ForEach-Object { $_.Trim() }
foreach ($line in $lines) {
    if ($line -match '^(журнал|диск|цикл|порядок|утверждение|инструмент):') { Write-Host $line }
}
$exported = ($lines | Where-Object { $_ -like "журнал: вынесен в /mnt/hs-journal.bin,*" }).Count -gt 0
if (-not $exported) {
    Write-Host "ПРИЁМКА: журнал не вынесен — проверять нечего" -ForegroundColor Red
    exit 2
}

# Достаём файл из образа на хосте. Монтирование только для чтения: приёмка не должна менять
# свидетельство, которое проверяет.
#
# F-ROOM-4 (08.11.2026). Раньше здесь стояло `Remove-Item $journal -ErrorAction SilentlyContinue`:
# ошибка удаления проглатывалась, и если файл был занят или не удалялся, прогон продолжался,
# а `cp` мог оставить ПРЕЖНИЙ журнал. Тогда приёмка и окно читали чужой результат — это
# корень F-ROOM-3 (на «раскажи стих» приходил ответ на «привет»).
#
# Теперь журнал обязан исчезнуть ДО прогона. Не исчез — прогон не начинается:
# лучше не получить результат, чем получить чужой.
$journal = Join-Path $runs "journal.bin"
if (Test-Path $journal) {
    Remove-Item $journal -Force -ErrorAction SilentlyContinue
    if (Test-Path $journal) {
        Write-Host "ПРИЁМКА: старый журнал не удаляется — прогон не начат (иначе результат будет чужим)" -ForegroundColor Red
        Write-Host "  файл: $journal" -ForegroundColor Red
        exit 4
    }
}
$wsl = "cd /mnt/c/111/herness && rm -rf /tmp/acc && mkdir -p /tmp/acc && e2fsck -fy /mnt/c/111/herness/$($Image -replace '\\','/') >/dev/null 2>&1; mount -o loop /mnt/c/111/herness/$($Image -replace '\\','/') /tmp/acc && cp /tmp/acc/hs-journal.bin /mnt/c/111/herness/runs/accept/journal.bin && umount /tmp/acc && echo вынуто"
wsl -e bash -lc $wsl
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $journal)) {
    Write-Host "ПРИЁМКА: не удалось вынуть журнал из образа" -ForegroundColor Red
    exit 2
}
Write-Host ("журнал на хосте: {0} байт" -f (Get-Item $journal).Length)

python (Join-Path $root "bin\accept.py") (Join-Path $root $Criteria) $journal
exit $LASTEXITCODE



