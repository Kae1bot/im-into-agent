# First-use setup: install wx-cli binaries + extract WeChat key
#
# Usage (new user, first activation):
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -PackagePath <zip>
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -DownloadUrl <zip-url>
#
# Steps:
#   1. Install wechat-cli.exe + libWCDB.dll to %LOCALAPPDATA%\wechat-cli\bin
#   2. Run "wechat-cli.exe cache refresh --force" to extract the key (WeChat must be logged in)
#   3. Report readiness
param(
  [string]$PackagePath = "",   # local zip containing wechat-cli.exe + libWCDB.dll
  [string]$DownloadUrl = "",   # URL of a hosted zip
  [string]$InstallDir = "$env:LOCALAPPDATA\wechat-cli"
)

$ErrorActionPreference = "Stop"
$binDir = Join-Path $InstallDir "bin"
$exe = Join-Path $binDir "wechat-cli.exe"
$dll = Join-Path $binDir "libWCDB.dll"

function Ensure-Binaries {
  if ((Test-Path $exe) -and (Test-Path $dll)) {
    Write-Host "Binaries already installed, skip."
    return
  }

  $zip = $null
  if ($PackagePath -ne "" -and (Test-Path $PackagePath)) {
    $zip = $PackagePath
  } elseif ($DownloadUrl -ne "") {
    $zip = Join-Path $env:TEMP "wx-cli-package.zip"
    Write-Host "Downloading $DownloadUrl ..."
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $zip -UseBasicParsing
  } else {
    throw "Need -PackagePath or -DownloadUrl to provide wechat-cli.exe + libWCDB.dll"
  }

  New-Item -ItemType Directory -Force -Path $binDir | Out-Null
  $tmp = Join-Path $env:TEMP "wx-cli-unpack"
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
  Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force

  $srcExe = Get-ChildItem $tmp -Recurse -Filter "wechat-cli.exe" -File | Select-Object -First 1
  $srcDll = Get-ChildItem $tmp -Recurse -Filter "libWCDB.dll" -File | Select-Object -First 1
  if (-not $srcExe -or -not $srcDll) { throw "zip is missing wechat-cli.exe or libWCDB.dll" }
  Copy-Item -LiteralPath $srcExe.FullName -Destination $exe -Force
  Copy-Item -LiteralPath $srcDll.FullName -Destination $dll -Force
  Write-Host "Installed to $binDir"
}

function Extract-Key {
  Write-Host "Extracting key (WeChat must be logged in)..."
  & $exe cache refresh --force
  if ($LASTEXITCODE -ne 0) {
    throw "cache refresh failed: log in to WeChat, open a chat window, then retry"
  }
  Write-Host "Key extracted."
}

Ensure-Binaries
Extract-Key

Write-Host "===== status ====="
& $exe status --pretty
Write-Host ""
Write-Host "Done. Agents can now read (read-only, no re-extraction):"
Write-Host ("  {0} resolve-chat ""<name>""" -f $exe)
Write-Host ("  {0} timeline ""<name>"" --after <start> --before <end> --limit 50" -f $exe)
