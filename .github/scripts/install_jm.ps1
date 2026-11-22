# Install the JustMarkets MT5 terminal into C:\Program Files\JustMarkets MetaTrader 5 and start it once
# (portable) so MQL5\Include exists. No login, no servers.dat, no EA: the folder is safe to cache.
# download.mql5.com refuses GitHub runner IPs at times (22 Nov 2026), so retry with a pause.
$ErrorActionPreference = "Continue"
$dir = "C:\Program Files\JustMarkets MetaTrader 5"
$urls = @("https://download.mql5.com/cdn/web/just.global.markets/mt5/justmarkets5setup.exe",
          "https://download.mql5.com/cdn/web/just.global.markets.ltd/mt5/justmarkets5setup.exe")
$ok = $false
for ($t = 1; $t -le 6 -and -not $ok; $t++) {
  foreach ($u in $urls) {
    Remove-Item jm.exe -ErrorAction SilentlyContinue
    curl.exe -sSL --connect-timeout 20 -m 180 -o jm.exe $u
    if ((Test-Path jm.exe) -and (Get-Item jm.exe).Length -gt 1000000) { $ok = $true; Write-Host "installer from $u (try $t)"; break }
  }
  if (-not $ok) { Write-Host "download try $t failed"; Start-Sleep -Seconds 30 }
}
if (-not $ok) {
  # fallback: a clean terminal folder packed from the owner's PC, encrypted (7z AES), release tag mt5pkg
  Write-Host "MT5 installer not reachable (download.mql5.com); trying the packed copy"
  if ($env:MT5_PKG_KEY) {
    gh release download mt5pkg -p "jm-mt5.7z" -O jm-mt5.7z --clobber 2>$null
    if (Test-Path jm-mt5.7z) {
      New-Item -ItemType Directory -Force -Path $dir | Out-Null
      7z x jm-mt5.7z "-p$env:MT5_PKG_KEY" "-o$dir" -y | Out-Null
      Remove-Item jm-mt5.7z -Force
    }
  }
  if (-not (Test-Path "$dir\metaeditor64.exe")) { Write-Host "no packed copy either"; exit 1 }
  $p = $null
}
if ($ok) {
  $p = Start-Process -FilePath .\jm.exe -ArgumentList "/auto" -PassThru
  for ($i = 0; $i -lt 120 -and -not $p.HasExited; $i++) { Start-Sleep -Seconds 5 }
  Start-Sleep -Seconds 20
}
Get-Process terminal64, metaeditor64 -ErrorAction SilentlyContinue | Stop-Process -Force
if (-not (Test-Path "$dir\terminal64.exe")) { Write-Host "installer ran but terminal64.exe is missing (it downloads the terminal from mql5 too)"; exit 1 }
$f = Start-Process -FilePath "$dir\terminal64.exe" -ArgumentList "/portable" -PassThru
for ($i = 0; $i -lt 24 -and -not (Test-Path "$dir\MQL5\Include\Trade\Trade.mqh"); $i++) { Start-Sleep -Seconds 5 }
Start-Sleep -Seconds 10
Get-Process terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force
if (-not (Test-Path "$dir\MQL5\Include\Trade\Trade.mqh") -or -not (Test-Path "$dir\metaeditor64.exe")) { Write-Host "terminal folder incomplete"; exit 1 }
# keep the cached copy clean: no accounts, logs or history from the first start
Remove-Item "$dir\Config\accounts.dat", "$dir\Config\common.ini" -Force -ErrorAction SilentlyContinue
Remove-Item "$dir\logs\*", "$dir\MQL5\Logs\*" -Force -Recurse -ErrorAction SilentlyContinue
Write-Host "terminal installed"
exit 0
