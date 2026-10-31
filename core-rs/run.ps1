# Быстрый цикл: собрать → упаковать → загрузить → проверить. Один прогон ≈ 6 секунд.
#
# Зачем отдельно от build.ps1: там `Start-Sleep -Seconds 30` и печать строк без проверки — это
# демонстрация, а не тест. Здесь ждём маркер «система жива», сверяем утверждения и падаем, если
# система загрузилась не так. Тогда «проверить в ядре» — это одна команда, а не ритуал.
param(
    [string]$Kernel = "vmlinuz-own-rng",
    [string]$Accel = "whpx",
    [string]$Mode = "loop",
    [int]$TimeoutSec = 20,
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$root = "C:\111\herness"
$core = Join-Path $root "core-rs"
$boot = Join-Path $core "boot"
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
$env:HS_MODE = $Mode

# Ожидания: что именно должно быть верно после загрузки. Список — не украшение: каждая строка
# это утверждение о системе, и прогон падает, если её нет.
$expected = @(
    "hs-core: я инициализировал систему сам, PID 1",
    "ядро: 6.18.60",
    "landlock ABI: 7",
    "namespaces:",
    "случайность ok"
)
if ($Mode -eq "loop-torn") {
    # Контрольный случай: журнал обрывается в госте, и проверка по файлу обязана это увидеть.
    $expected += @("цикл: шагов 1, вызовов 1", "оборван на 4 байта", "порядок из файла: НАРУШЕН")
} elseif ($Mode -eq "loop") {
    # В режиме цикла проверяется не только загрузка, но и порядок событий: run/start → call →
    # result → step → run/end, и отдельный коммит.
    $expected += @("цикл: шагов 1, вызовов 1", "порядок ok", "коммитов 1", "порядок из файла: ok")
} else {
    $expected += @("журнал:")
}

$watch = [Diagnostics.Stopwatch]::StartNew()

if (-not $SkipBuild) {
    $mingw = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Directory -ErrorAction SilentlyContinue |
        Where-Object Name -match 'WinLibs' |
        ForEach-Object { Join-Path $_.FullName "mingw64\bin" } |
        Where-Object { Test-Path (Join-Path $_ "x86_64-w64-mingw32-gcc.exe") } |
        Select-Object -First 1
    $env:Path = "$env:USERPROFILE\.cargo\bin;$mingw;$env:Path"
    $env:CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER = "rust-lld"
    Push-Location $core
    try {
        cargo build --release --target x86_64-unknown-linux-musl 2>&1 | Select-Object -Last 1
        if ($LASTEXITCODE -ne 0) { Write-Error "сборка не прошла" }
    } finally { Pop-Location }
}

python (Join-Path $root "bin\make_initramfs.py") | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "упаковка initramfs не прошла" }

$out = Join-Path $boot "run-out.txt"
$err = Join-Path $boot "run-out.err"
Remove-Item $out, $err -ErrorAction SilentlyContinue

$args = @('-m', '256', '-smp', '1')
if ($Accel -ne "none") { $args += @('-accel', $Accel) }
$args += @('-kernel', (Join-Path $boot $Kernel),
           '-initrd', (Join-Path $boot 'initramfs.cpio.gz'),
           # Источник энтропии: без него getrandom в гостевой системе может не иметь источника,
           # а Rust-овский HashMap дергает его при первом же использовании.
           '-device', 'virtio-rng-pci',
           '-append', '"console=ttyS0 panic=-1"',
           '-nographic', '-no-reboot')
$process = Start-Process -FilePath $qemu -ArgumentList $args -RedirectStandardOutput $out -RedirectStandardError $err -PassThru

# Ждём маркер, а не фиксированные 30 секунд: загрузка под WHPX — около 0.5 с до init.
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$text = ""
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 150
    $text = (Get-Content $out -Raw -ErrorAction SilentlyContinue) -as [string]
    if ($text -and $text.Contains("система жива")) { break }
    if ($process.HasExited) { break }
}
if (-not $process.HasExited) { $process.Kill() }
$watch.Stop()

$lines = ($text -split "`n") | ForEach-Object { $_.Trim() }
$bootLine = $lines | Where-Object { $_ -like "время до init:*" } | Select-Object -First 1
$missing = @()
foreach ($needle in $expected) {
    if (-not ($lines | Where-Object { $_ -like "*$needle*" })) { $missing += $needle }
}

Write-Host ("ядро: {0}, ускорение: {1}" -f $Kernel, $(if ($Accel -eq "none") { "нет" } else { $Accel }))
if ($bootLine) { Write-Host $bootLine }
Write-Host ("цикл целиком: {0:N1} с" -f $watch.Elapsed.TotalSeconds)
if ($missing.Count -gt 0) {
    Write-Host "[FAIL] не найдено в выводе:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" }
    Write-Host "--- stderr ---"
    Get-Content $err -ErrorAction SilentlyContinue | Select-Object -First 5
    exit 1
}
Write-Host "[ok] все ожидания найдены" -ForegroundColor Green
exit 0
