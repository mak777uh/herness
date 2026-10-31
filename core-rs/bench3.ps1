# Три прогона бенча на политику: скорость в QEMU нестабильна, нужна медиана.
$ErrorActionPreference = "Stop"
$root = "C:\111\herness"
$core = Join-Path $root "core-rs"
$boot = Join-Path $core "boot"
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
$env:HS_KERNEL = "vmlinuz-own"
$image = Join-Path $boot "journal.img"

function Fresh-Image {
    wsl -d Ubuntu-24.04 -u root -- bash -lc "cd /mnt/c/111/herness/core-rs/boot && rm -f journal.img && dd if=/dev/zero of=journal.img bs=1M count=64 status=none && mkfs.ext4 -q -F journal.img" *> $null
}

function Bench([string]$mode) {
    Fresh-Image
    $env:HS_MODE = $mode
    python (Join-Path $root "bin\make_initramfs.py") *> $null
    $log = Join-Path $boot "bench-$mode.txt"
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
    $deadline = (Get-Date).AddSeconds(90)
    $value = $null
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 300
        if (Test-Path $log) {
            $hit = Get-Content $log -ErrorAction SilentlyContinue | Select-String -Pattern '^бенч .*= (\d+) записей/с' | Select-Object -Last 1
            if ($hit) { $value = [int]$hit.Matches.Groups[1].Value; break }
        }
        if ($process.HasExited) { break }
    }
    if (-not $process.HasExited) { $process.Kill() }
    return $value
}

$results = @{}
foreach ($mode in @("bench-write", "bench-batch")) {
    $values = @()
    for ($i = 1; $i -le 3; $i++) {
        $value = Bench $mode
        if ($value) { $values += $value }
        Write-Host "$mode прогон $i : $value"
    }
    if ($values.Count -gt 0) {
        $sorted = $values | Sort-Object
        $median = $sorted[[int][math]::Floor($sorted.Count / 2)]
        Write-Host "$mode : медиана $median записей/с (все: $($values -join ', '))"
        $results[$mode] = $median
    }
}
$results | Format-Table -AutoSize | Out-String
