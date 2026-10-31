# Загрузка образа в QEMU с выводом метрик: ядро, Landlock ABI, время до init, хеш.
param(
    [string]$Kernel = "vmlinuz-lts",
    [int]$Seconds = 25
)
$ErrorActionPreference = "Stop"
$boot = "C:\111\herness\core-rs\boot"
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
$out = Join-Path $boot ("boot-" + [System.IO.Path]::GetFileNameWithoutExtension($Kernel) + ".txt")
$err = "$out.err"
Remove-Item $out, $err -ErrorAction SilentlyContinue

$args = @('-m', '256', '-smp', '1', '-kernel', (Join-Path $boot $Kernel),
          '-initrd', (Join-Path $boot 'initramfs.cpio.gz'),
          '-append', '"console=ttyS0 panic=-1"', '-nographic', '-no-reboot')
$p = Start-Process -FilePath $qemu -ArgumentList $args -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
Start-Sleep -Seconds $Seconds
if (-not $p.HasExited) { $p.Kill() }
Start-Sleep -Milliseconds 500

$kernelLine = (Get-Content $out -ErrorAction SilentlyContinue | Select-String -Pattern '^ядро: ' | Select-Object -First 1).Line
$abiLine = (Get-Content $out -ErrorAction SilentlyContinue | Select-String -Pattern '^landlock ABI: ' | Select-Object -First 1).Line
$timeLine = (Get-Content $out -ErrorAction SilentlyContinue | Select-String -Pattern '^время до init: ' | Select-Object -First 1).Line
$alive = [bool](Get-Content $out -ErrorAction SilentlyContinue | Select-String -Pattern 'hs-core: система жива')
$sizeMb = [math]::Round((Get-Item (Join-Path $boot $Kernel)).Length / 1MB, 2)
$panic = [bool](Get-Content $out -ErrorAction SilentlyContinue | Select-String -Pattern 'Kernel panic - not syncing')

[pscustomobject]@{
    ядро = if ($kernelLine) { $kernelLine -replace '^ядро: ','' } else { "не загрузилось" }
    ABI = if ($abiLine) { $abiLine -replace '^landlock ABI: ','' } else { "?" }
    до_init_с = if ($timeLine) { $timeLine -replace '^время до init: ','' } else { "?" }
    размер_МБ = $sizeMb
    жива = $alive
    паника = $panic
} | Format-List | Out-String
