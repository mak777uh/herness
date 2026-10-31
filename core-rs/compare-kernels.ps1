# Сравнение ядер-кандидатов: версия, Landlock ABI, размер, загрузка.
$ErrorActionPreference = "Continue"
$boot = "C:\111\herness\core-rs\boot"
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
$initrd = Join-Path $boot "initramfs.cpio.gz"

$candidates = @(
    @{ name = "alpine-3.20"; url = "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/netboot/vmlinuz-lts" },
    @{ name = "alpine-3.21"; url = "https://dl-cdn.alpinelinux.org/alpine/v3.21/releases/x86_64/netboot/vmlinuz-lts" },
    @{ name = "alpine-3.22"; url = "https://dl-cdn.alpinelinux.org/alpine/v3.22/releases/x86_64/netboot/vmlinuz-lts" },
    @{ name = "alpine-latest"; url = "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/netboot/vmlinuz-lts" }
)

$results = @()
foreach ($candidate in $candidates) {
    $target = Join-Path $boot ("vmlinuz-" + $candidate.name)
    if (-not (Test-Path $target)) {
        curl.exe -sS -L --max-time 120 -o $target $candidate.url 2>$null
    }
    if (-not (Test-Path $target) -or (Get-Item $target).Length -lt 1000000) {
        Write-Host ("{0}: нет ядра" -f $candidate.name)
        continue
    }
    $sizeMb = [math]::Round((Get-Item $target).Length / 1MB, 1)
    $out = Join-Path $boot ("out-" + $candidate.name + ".txt")
    $err = Join-Path $boot ("err-" + $candidate.name + ".txt")
    Remove-Item $out, $err -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $qemu -ArgumentList @(
        '-m', '256', '-kernel', $target, '-initrd', $initrd,
        '-append', '"console=ttyS0 panic=-1"', '-nographic', '-no-reboot'
    ) -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    Start-Sleep -Seconds 22
    if (-not $p.HasExited) { $p.Kill() }
    $lines = Get-Content $out -ErrorAction SilentlyContinue
    $kernel = ($lines | Select-String -Pattern '^ядро: ' | Select-Object -First 1).Line
    $abi = ($lines | Select-String -Pattern '^landlock ABI: ' | Select-Object -First 1).Line
    $booted = [bool]($lines | Select-String -Pattern 'hs-core: система жива')
    $results += [pscustomobject]@{
        кандидат = $candidate.name
        размер_МБ = $sizeMb
        ядро = if ($kernel) { $kernel -replace '^ядро: ', '' } else { "нет" }
        abi = if ($abi) { $abi -replace '^landlock ABI: ', '' } else { "0" }
        загрузилось = $booted
    }
}

$results | Format-Table -AutoSize | Out-String
