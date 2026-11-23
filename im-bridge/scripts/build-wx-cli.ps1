# Build Windows wx-cli: wechat-cli.exe + libWCDB.dll
#
# Prereqs (developer machine):
#   - Go >= 1.26
#   - CMake >= 3.31
#   - Visual Studio 2022 BuildTools (C++ desktop workload, MSVC 19.4x)
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-wx-cli.ps1
#
# Output: out\wechat-cli.exe + out\libWCDB.dll
#
# Note: the official release currently only ships macOS (darwin-arm64); this
#       script compiles the Windows binaries from source for skill distribution.
param(
  [string]$OutDir = "out",
  [string]$WorkDir = "$env:TEMP\wx-cli-build",
  [string]$WcdbVersion = "2.1.16"
)

$ErrorActionPreference = "Stop"

# ---- prerequisites ----
if (-not (Get-Command go -ErrorAction SilentlyContinue)) {
  throw "Go toolchain required: https://go.dev/dl/ (>= 1.26)"
}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
  throw "CMake required: https://cmake.org/download/ (>= 3.31)"
}

# ---- pinned WCDB source (Tencent/wcdb 2.1.16) ----
$WCDB_URL    = "https://github.com/Tencent/wcdb/releases/download/v2.1.16/wcdb-2.1.16.zip"
$WCDB_SHA256 = "260845053c5dedc4578570203a5ba235c3be1e74a671c2fc1aeb12c988dd5346"

$sourceRoot = Split-Path -Parent $PSScriptRoot
$outAbs = Join-Path $sourceRoot $OutDir
New-Item -ItemType Directory -Force -Path $outAbs | Out-Null

$archive  = Join-Path $WorkDir "wcdb-$WcdbVersion.zip"
$extract  = Join-Path $WorkDir "src"
$buildDir = Join-Path $WorkDir "build"

# ---- 1. download and verify WCDB source ----
if (Test-Path $WorkDir) { Remove-Item $WorkDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $WorkDir, $extract | Out-Null

Write-Host "Downloading WCDB source ..."
Invoke-WebRequest -Uri $WCDB_URL -OutFile $archive -UseBasicParsing
$got = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($got -ne $WCDB_SHA256) { throw "WCDB source SHA256 mismatch: $got" }
Write-Host "WCDB source SHA256 OK"
Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force

$srcDir = Join-Path $extract "wcdb-$WcdbVersion\src"
if (-not (Test-Path $srcDir)) { throw "WCDB source dir not found: $srcDir" }

# ---- 2. build WCDB -> libWCDB.dll ----
# WCDB bundles prebuilt Windows OpenSSL (libcrypto.lib), so no separate OpenSSL build.
Write-Host "cmake configure ..."
cmake -S $srcDir -B $buildDir -G "Visual Studio 17 2022" -A x64 `
  -DBUILD_SHARED_LIBS=ON `
  -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded `
  "-DCMAKE_C_FLAGS=/DSQLITE_API=__declspec(dllexport)"
if ($LASTEXITCODE -ne 0) { throw "cmake configure failed" }

Write-Host "cmake build WCDB ..."
cmake --build $buildDir --config Release --target WCDB --parallel
if ($LASTEXITCODE -ne 0) { throw "cmake build failed" }

$dll = Get-ChildItem $buildDir -Recurse -Filter "WCDB.dll" -File |
  Where-Object { $_.FullName -match "\\Release\\" } |
  Sort-Object Length -Descending | Select-Object -First 1
if (-not $dll) { throw "WCDB.dll not produced" }
Copy-Item -LiteralPath $dll.FullName -Destination (Join-Path $outAbs "libWCDB.dll") -Force
Write-Host "libWCDB.dll -> $outAbs\libWCDB.dll"

# ---- 3. build Go exe ----
Write-Host "go build wechat-cli.exe ..."
$wxcliDir = Join-Path $sourceRoot "wx-cli"
if (-not (Test-Path $wxcliDir)) { throw "wx-cli source not found: $wxcliDir" }
Push-Location $wxcliDir
try {
  go build -o (Join-Path $outAbs "wechat-cli.exe") ./cmd/wechat-cli
  if ($LASTEXITCODE -ne 0) { throw "go build failed" }
} finally {
  Pop-Location
}
Write-Host "wechat-cli.exe -> $outAbs\wechat-cli.exe"

# ---- 4. report artifacts ----
Write-Host "===== artifacts ====="
Get-ChildItem $outAbs -File | ForEach-Object {
  $h = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  Write-Host ("{0}`t{1} bytes`tsha256={2}" -f $_.Name, $_.Length, $h)
}

# Sandbox-only notes (not needed on a normal machine):
#   - TLS cert verify fails  -> set SSL_CERT_FILE to a CA bundle (e.g. certifi cacert.pem)
#   - proxy.golang.org unreachable -> GOPROXY=https://goproxy.cn,direct
#   - MSBuild cannot write %TEMP%\MSBuildTemp -> redirect TEMP/TMP to a writable dir
#   - build dir under temp triggers MSB8029 -> keep the build dir outside temp
