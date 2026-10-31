# Обрыв на цикле: пишем цикл на диск, убиваем ВМ, читаем блоки прогонов.
#
# Проверяет не «журнал пишется», а интеграцию: цикл (ADR-0040) + долговечность (C-0121).
# Критерий: после убийства целые блоки читаются, оборванных — не больше одного, и оборванный
# не считается целым.
$ErrorActionPreference = "Stop"
$root = "C:\111\herness"
$core = Join-Path $root "core-rs"
$boot = Join-Path $core "boot"
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
$kernel = "vmlinuz-own-rng"
$image = Join-Path $boot "loop.img"

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
    if ($LASTEXITCODE -ne 0) { throw 'сборка не прошла' }
} finally { Pop-Location }

function Reset-Disk {
    # Свежий ext4-образ: иначе результат зависит от прошлых прогонов.
    wsl -d Ubuntu-24.04 -u root -- bash -lc "cd /mnt/c/111/herness/core-rs/boot && rm -f loop.img && dd if=/dev/zero of=loop.img bs=1M count=64 status=none && mkfs.ext4 -q -F loop.img" *> $null
    if (-not (Test-Path $image)) { throw 'образ диска не создан' }
}

function Start-Vm([string]$mode, [string]$log) {
    $env:HS_MODE = $mode
    python (Join-Path $root "bin\make_initramfs.py") *> $null
    Remove-Item $log -ErrorAction SilentlyContinue
    $arguments = @(
        '-m', '256', '-smp', '1', '-accel', 'whpx',
        '-kernel', (Join-Path $boot $kernel),
        '-initrd', (Join-Path $boot 'initramfs.cpio.gz'),
        '-device', 'virtio-rng-pci',
        '-append', '"console=ttyS0 panic=-1"',
        '-drive', ("file=" + $image + ",format=raw,if=virtio"),
        '-nographic', '-no-reboot'
    )
    return Start-Process -FilePath $qemu -ArgumentList $arguments -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru
}

# 1. Пишем цикл на диск и убиваем ВМ на середине.
Reset-Disk
$writeLog = Join-Path $boot "loop-repeat.txt"
$writer = Start-Vm "loop-repeat" $writeLog
Start-Sleep -Seconds 6
if (-not $writer.HasExited) { $writer.Kill() }
Start-Sleep -Milliseconds 400
$written = (Get-Content $writeLog -ErrorAction SilentlyContinue | Select-String 'прогонов:').Line

# 2. Читаем то, что осталось.
$checkLog = Join-Path $boot "loop-verify.txt"
$checker = Start-Vm "loop-verify" $checkLog
$checker.WaitForExit(30000) | Out-Null
if (-not $checker.HasExited) { $checker.Kill(); throw 'проверка не уложилась в 30 секунд' }

$lines = Get-Content $checkLog -ErrorAction SilentlyContinue
$report = ($lines | Select-String 'блоков').Line
$tail = if ($report -match 'хвост (\d+)') { [int]$Matches[1] } else { -1 }
$broken = if ($report -match 'битых (\d+)') { [int]$Matches[1] } else { -1 }

Write-Host ("запись: {0}" -f ($written | Select-Object -Last 1))
Write-Host ("после обрыва: {0}" -f $report)
($lines | Select-String '\[!\]').Line | ForEach-Object { Write-Host "  $_" }

if (-not $report) { Write-Host "[FAIL] отчёт о блоках не найден" -ForegroundColor Red; exit 1 }
if ($checker.ExitCode -ne 0) { Write-Host "[FAIL] проверка вернула $($checker.ExitCode)" -ForegroundColor Red; exit 1 }
if ($broken -gt 1) { Write-Host "[FAIL] битых блоков больше одного: $broken" -ForegroundColor Red; exit 1 }

# Обрыв одного прогона занимает десятки миллисекунд, а хост-кэш QEMU переживает убийство
# процесса — поэтому оборванный блок воспроизводится не каждый раз. Это не «успех» и не «провал»:
# здесь проверяется, что начатые блоки читаются целиком и ни один не принят частично.
if ($broken -eq 1) {
    Write-Host ("[ok] оборванный блок не принят за целый (хвост {0} байт)" -f $tail) -ForegroundColor Green
} else {
    Write-Host "[ok] после убийства ВМ все блоки целые: частично записанных не принято" -ForegroundColor Green
}
exit 0
