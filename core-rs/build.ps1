# Сборка ядра харнесса на Windows без WSL: кросс-сборка, упаковка, загрузка в QEMU.
# Требует: rustup (windows-gnu), mingw-w64 (WinLibs), qemu, python.

$ErrorActionPreference = "Stop"
$root = "C:\111\herness"
$core = Join-Path $root "core-rs"
$boot = Join-Path $core "boot"
$mingw = "C:\Users\$env:USERNAME\AppData\Local\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin"

if (-not (Test-Path $mingw)) {
    $found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Directory -ErrorAction SilentlyContinue |
        Where-Object Name -match 'WinLibs' |
        ForEach-Object { Join-Path $_.FullName "mingw64\bin" } |
        Where-Object { Test-Path (Join-Path $_ "x86_64-w64-mingw32-gcc.exe") } |
        Select-Object -First 1
    if ($found) { $mingw = $found } else { Write-Error "не найден mingw-w64 (WinLibs)" }
}

$env:Path = "$env:USERPROFILE\.cargo\bin;$mingw;$env:Path"
$env:CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER = "rust-lld"

Write-Host "--- сборка (кросс, статический musl) ---"
Push-Location $core
try {
    cargo build --release --target x86_64-unknown-linux-musl 2>&1 | Select-Object -Last 2
} finally {
    Pop-Location
}

$binary = Join-Path $core "target\x86_64-unknown-linux-musl\release\hs-core"
if (-not (Test-Path $binary)) { Write-Error "бинарник не собрался" }
$size = (Get-Item $binary).Length
$magic = ([System.IO.File]::ReadAllBytes($binary)[0..3] | ForEach-Object { $_.ToString('X2') }) -join ' '
Write-Host "бинарник: $size байт, сигнатура $magic"

Write-Host "--- упаковка initramfs ---"
python (Join-Path $root "bin\make_initramfs.py")

Write-Host "--- загрузка в QEMU (30 с) ---"
New-Item -ItemType Directory -Path $boot -Force | Out-Null
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
if (-not (Test-Path $qemu)) { Write-Error "не найден qemu-system-x86_64.exe" }
$outFile = Join-Path $boot "qemu-out.txt"
$errFile = Join-Path $boot "qemu-out.err"
Remove-Item $outFile, $errFile -ErrorAction SilentlyContinue
$arguments = @('-m', '256', '-smp', '1', '-kernel', (Join-Path $boot $(if ($env:HS_KERNEL) { $env:HS_KERNEL } else { 'vmlinuz-own' })), '-initrd', (Join-Path $boot 'initramfs.cpio.gz'),
               '-append', '"console=ttyS0 panic=-1"', '-nographic', '-no-reboot')
$process = Start-Process -FilePath $qemu -ArgumentList $arguments -RedirectStandardOutput $outFile -RedirectStandardError $errFile -PassThru
Start-Sleep -Seconds 30
if (-not $process.HasExited) { $process.Kill() }

$lines = Get-Content $outFile -ErrorAction SilentlyContinue | Select-String -Pattern 'hs-core|печать /method|архитектура|ядро:|landlock|время до init'
$lines | ForEach-Object { $_.Line }
if ($lines.Count -lt 2) {
    Write-Host "--- stderr ---"
    Get-Content $errFile -ErrorAction SilentlyContinue | Select-Object -First 5
    Write-Error "система не загрузилась как ожидалось"
}
Write-Host "готово: ядро + hs-core загружены без WSL"
