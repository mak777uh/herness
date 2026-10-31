# Опыт долговечности: две политики (fsync на коммит против пакета), убийство ВМ, чтение после.
$ErrorActionPreference = "Stop"
$root = "C:\111\herness"
$core = Join-Path $root "core-rs"
$boot = Join-Path $core "boot"
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
$mingw = "C:\Users\$env:USERNAME\AppData\Local\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin"
$env:Path = "$env:USERPROFILE\.cargo\bin;$mingw;$env:Path"
$env:CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER = "rust-lld"
$env:HS_KERNEL = "vmlinuz-own"
$image = Join-Path $boot "journal.img"

Push-Location $core
cargo build --release --target x86_64-unknown-linux-musl *> $null
Pop-Location

function Start-Vm([string]$mode) {
    $env:HS_MODE = $mode
    python (Join-Path $root "bin\make_initramfs.py") *> $null
    $log = Join-Path $boot "durability-$mode.txt"
    Remove-Item $log -ErrorAction SilentlyContinue
    $arguments = @(
        '-m', '256', '-smp', '1',
        '-kernel', (Join-Path $boot 'vmlinuz-own'),
        '-initrd', (Join-Path $boot 'initramfs.cpio.gz'),
        '-append', '"console=ttyS0 panic=-1"',
        '-drive', ("file=" + $image + ",format=raw,if=virtio"),
        '-nographic', '-no-reboot'
    )
    $process = Start-Process -FilePath $qemu -ArgumentList $arguments -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru
    $script:lastLog = $log
    return $process
}

function Run-Crash([string]$mode) {
    wsl -d Ubuntu-24.04 -u root -- bash -lc "cd /mnt/c/111/herness/core-rs/boot && rm -f journal.img && dd if=/dev/zero of=journal.img bs=1M count=64 status=none && mkfs.ext4 -q -F journal.img" *> $null
    Write-Host "=== политика: $mode ==="
    $process = Start-Vm $mode
    $deadline = (Get-Date).AddSeconds(40)
    $confirmed = 0
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
        if (-not (Test-Path $script:lastLog)) { continue }
        $line = Get-Content $script:lastLog -ErrorAction SilentlyContinue |
            Select-String -Pattern '^подтверждено: commit-(\d+)' | Select-Object -Last 1
        if ($line) {
            $confirmed = [int]$line.Matches.Groups[1].Value
            if ($confirmed -ge 5) { break }
        }
        if ($process.HasExited) { break }
    }
    Start-Sleep -Milliseconds 400
    if (-not $process.HasExited) { $process.Kill() }
    Start-Sleep -Milliseconds 800
    Write-Host "подтверждённых коммитов до убийства: $confirmed"

    $check = Start-Vm "check"
    Start-Sleep -Seconds 22
    if (-not $check.HasExited) { $check.Kill() }
    Start-Sleep -Milliseconds 500
    Get-Content $script:lastLog | Select-String -Pattern '^журнал на диске:' | ForEach-Object { $_.Line }
}

Run-Crash "write"
Run-Crash "batch"
