# Живой обрыв: убить ВМ посреди работы, поднять снова и продолжить тот же прогон.
#
# Зачем: продолжение после обрыва было проверено на синтетическом журнале (loop-resume). Здесь
# проверяется то, что происходит на самом деле: питание пропадает посреди шага, журнал остаётся на
# диске (частично записанным), и второй запуск обязан продолжить, а не начать заново.
#
# Порядок:
#   1. образ с файлами репозитория копируется в рабочий (acc.img), журнал живёт на нём;
#   2. первый запуск: ждём первые шаги, затем убиваем QEMU — как обрыв питания;
#   3. второй запуск: тот же образ, та же задача — комната должна сказать «продолжение: шагов N»;
#   4. приёмка на хосте по вынесенному журналу.
param(
    [string]$Criteria = "accept/room-claims-statistics-v3.json",
    [string]$Task = "Найди в /mnt/CLAIMS.md утверждение типа statistics и назови его id вида C-1234. Ответь одной строкой: id и цитата.",
    [int]$KillAfterSec = 9,
    [int]$TimeoutSec = 240
)
$ErrorActionPreference = "Stop"
$root = "C:\111\herness"
$core = Join-Path $root "core-rs"
$boot = Join-Path $core "boot"
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
# Образ берётся из манифеста комнаты (F-0073/N7): путь не живёт в двух местах.
# Раньше $image был жёстко acc.img, а источником служил устаревший share.img.
$room = Join-Path $root "lab\room.json"
$imageRel = (Get-Content $room -Raw | ConvertFrom-Json).image
if (-not $imageRel) { Write-Host "ПРОВАЛ: в lab/room.json нет поля image"; exit 3 }
$image = Join-Path $root $imageRel
$env:HS_MODE = "loop-bridge-resume"
$env:HS_TASK = $Task
$env:HS_BRIDGE_TOKEN = (Get-Content "C:\111\env\bridge-token.txt" -Raw).Trim()
$env:HS_BRIDGE_MODEL = "deepseek-v4.1-flash"
$spec = Get-Content (Join-Path $root $Criteria) -Raw | ConvertFrom-Json
$budget = [ordered]@{ steps = [int]$spec.max_steps; seconds = 240; allowance = [double]$spec.max_allowance }
$env:HS_BUDGET = ($budget | ConvertTo-Json -Compress)

python (Join-Path $root "bin\make_initramfs.py") | Out-Null
if ($LASTEXITCODE -ne 0) { throw "упаковка initramfs не прошла" }
# N7 (F-0073): раньше здесь Copy-Item share.img -> acc.img подменял свежий образ
# устаревшим share.img (он не пересобирается с цикла fast-gate; NC2: --check FAIL,
# 6 docs / 8 failures назад). Теперь образ пересобирается из манифеста — чистый и
# текущий; журнал первого запуска ляжет на него и переживёт обрыв питания.
python (Join-Path $root "bin\build_room.py") --build
if ($LASTEXITCODE -ne 0) { Write-Host "ПРОВАЛ: образ комнаты не пересобран — прогон не начат"; exit 3 }

function Start-Room([string]$log) {
    $args = @('-m', '512', '-smp', '1', '-accel', 'whpx',
              '-netdev', 'user,id=n0', '-device', 'virtio-net-pci,netdev=n0',
              '-kernel', (Join-Path $boot 'vmlinuz-own-net'),
              '-initrd', (Join-Path $boot 'initramfs.cpio.gz'),
              '-device', 'virtio-rng-pci',
              '-drive', "file=$image,format=raw,if=virtio",
              '-append', '"console=ttyS0 panic=-1 ip=dhcp"',
              '-nographic', '-no-reboot')
    return Start-Process -FilePath $qemu -ArgumentList $args -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru
}

# --- фаза 1: начать и оборвать
$first = Join-Path $boot "crash-1.txt"
Remove-Item $first, "$first.err" -ErrorAction SilentlyContinue
$proc = Start-Room $first
Write-Host "первый запуск: ждём $KillAfterSec с и убиваем"
Start-Sleep -Seconds $KillAfterSec
if (-not $proc.HasExited) { $proc.Kill(); $proc.WaitForExit(5000) | Out-Null }
$text1 = (Get-Content $first -Raw -ErrorAction SilentlyContinue) -as [string]
$calls = ([regex]::Matches($text1, 'tool/call')).Count
Write-Host ("до обрыва в журнале комнаты: строк с tool/call {0}" -f $calls)

# --- фаза 2: поднять тот же образ и посмотреть, продолжит ли
$second = Join-Path $boot "crash-2.txt"
Remove-Item $second, "$second.err" -ErrorAction SilentlyContinue
$proc2 = Start-Room $second
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$text2 = ""
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 200
    $text2 = (Get-Content $second -Raw -ErrorAction SilentlyContinue) -as [string]
    if ($text2 -and $text2.Contains("система жива")) { break }
    if ($proc2.HasExited) { break }
}
if (-not $proc2.HasExited) { $proc2.Kill() }
$lines2 = ($text2 -split "`n") | ForEach-Object { $_.Trim() }
$resumedLine = $lines2 | Where-Object { $_ -like "продолжение: шагов*" } | Select-Object -First 1
$totalLine = $lines2 | Where-Object { $_ -like "итог журнала:*" } | Select-Object -First 1
Write-Host "второй запуск: $resumedLine"
Write-Host "второй запуск: $totalLine"

if (-not $resumedLine) {
    Write-Host "ПРОВАЛ: второй запуск не увидел незакрытый журнал" -ForegroundColor Red
    exit 2
}

# --- приёмка на хосте
$journal = Join-Path $root "runs\accept\journal-crash.bin"
Remove-Item $journal -ErrorAction SilentlyContinue
# Извлечение — через helper (этап 1.6, READONLY-ACCEPT-R1): копия образа, SHA-256 оригинала
# до/после, оригинал не чинится на месте. Приёмка не меняет улику (ADR-0049).
python (Join-Path $root "bin\extract_journal.py") $image $journal
python (Join-Path $root "bin\accept.py") (Join-Path $root $Criteria) $journal
exit $LASTEXITCODE
