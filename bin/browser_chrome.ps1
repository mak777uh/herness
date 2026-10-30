# browser_chrome.ps1 — поднять Chrome с отладочным портом для hs browser (CDP)
#
# Закрывает Chrome, копирует cookie в отдельный профиль и запускает браузер с CDP.
# Профиль копируется, потому что Chrome держит Network\Cookies занятым, пока работает,
# а Cloudflare/Google пропускают только браузер с живыми cookie.
#
# Использование:  powershell -File bin/browser_chrome.ps1 [-Port 9222]

param(
    [int]$Port = 9222
)

$ErrorActionPreference = 'Stop'
$src = Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data'
$dst = 'C:\111\chrome-cdp'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'

if (-not (Test-Path $chrome)) { throw "Chrome не найден: $chrome" }
if (-not (Test-Path $src)) { throw "Профиль Chrome не найден: $src" }

$running = Get-Process chrome -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "Chrome запущен ($($running.Count) процессов) — cookie может быть занят. Закрой Chrome для надёжности."
}

New-Item -ItemType Directory -Force -Path (Join-Path $dst 'Default\Network') | Out-Null
$files = @('Local State', 'Default\Preferences', 'Default\Secure Preferences',
           'Default\Network\Cookies', 'Default\Login Data', 'Default\Web Data')
foreach ($rel in $files) {
    $from = Join-Path $src $rel
    $to = Join-Path $dst $rel
    if (Test-Path $from) {
        try { Copy-Item $from $to -Force; Write-Host "скопировано: $rel" }
        catch { Write-Host "не удалось: $rel ($($_.Exception.GetType().Name))" }
    }
}

$proc = Start-Process -FilePath $chrome -PassThru -ArgumentList @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$dst",
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank'
)
Start-Sleep -Seconds 8
Write-Host "Chrome запущен (pid $($proc.Id)), CDP: http://127.0.0.1:$Port"
Write-Host "Проверка: python bin/hs.py browser `"nixos release notes`""
