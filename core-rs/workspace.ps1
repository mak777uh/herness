# Рабочий образ: собрать ext4-образ с настоящими файлами репозитория для комнаты.
#
# Зачем: 9p (общий каталог) на Windows-QEMU недоступен — `-virtfs` собран без поддержки
# (проверено: "virtfs support is disabled"). Значит файлы попадают в гостя копией в образе.
# Это не «живой» каталог: после правок на хосте образ надо пересобрать — и это видно в команде.
$ErrorActionPreference = "Stop"
$root = "C:\111\herness"
$image = Join-Path $root "share.img"
$staging = "/mnt/c/111/herness/share"

# Что кладём: ровно то, что модели может понадобиться, и ничего лишнего.
$items = @(
    "CLAIMS.md",
    "README.md",
    "NOT-CLAIMED.md",
    "docs",
    "lab/failures"
)

Write-Host "--- подготовка каталога ---"
if (Test-Path (Join-Path $root "share")) { Remove-Item -Recurse -Force (Join-Path $root "share") }
New-Item -ItemType Directory -Force -Path (Join-Path $root "share") | Out-Null
foreach ($item in $items) {
    $source = Join-Path $root $item
    if (-not (Test-Path $source)) { Write-Host "  нет $item — пропуск"; continue }
    $target = Join-Path (Join-Path $root "share") (Split-Path $item -Leaf)
    if ((Get-Item $source).PSIsContainer) {
        Copy-Item $source $target -Recurse -Force
    } else {
        Copy-Item $source $target -Force
    }
    Write-Host "  добавлено: $item"
}

Write-Host "--- образ ---"
wsl -e bash -lc "cd /mnt/c/111/herness && rm -f share.img && dd if=/dev/zero of=share.img bs=1M count=64 status=none && mkfs.ext4 -q -F share.img && rm -rf /tmp/ws && mkdir -p /tmp/ws && mount -o loop share.img /tmp/ws && cp -r $staging/. /tmp/ws/ && sync && umount /tmp/ws && echo готово"
if (-not (Test-Path $image)) { Write-Error "образ не создан" }
$size = (Get-Item $image).Length
$files = (Get-ChildItem (Join-Path $root "share") -Recurse -File | Measure-Object).Count
Write-Host ("образ: {0} байт, файлов внутри: {1}" -f $size, $files)
