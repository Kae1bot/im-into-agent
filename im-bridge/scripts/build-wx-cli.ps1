param(
    [string]$BuildRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'build\native'),
    [string]$Go = 'go',
    [string]$CMake = 'cmake'
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($BuildRoot)
$work = Join-Path $root ('work-' + [guid]::NewGuid().ToString('N'))
$bin = Join-Path $root 'bin'
$tmp = Join-Path $work 'tmp'
New-Item -ItemType Directory -Path $work, $bin, $tmp -Force | Out-Null

$commit = '7d8b1ce46dac5eeae1fe852178b57803c0716c94'
$wxArchive = Join-Path $work 'wx-cli.zip'
$wcdbArchive = Join-Path $work 'wcdb.zip'
Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/r266-tech/wx-cli/zip/$commit" -OutFile $wxArchive
Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/Tencent/wcdb/releases/download/v2.1.16/wcdb-2.1.16.zip' -OutFile $wcdbArchive
if ((Get-FileHash -LiteralPath $wcdbArchive -Algorithm SHA256).Hash -ne
    '260845053c5dedc4578570203a5ba235c3be1e74a671c2fc1aeb12c988dd5346') {
    throw 'The WCDB archive SHA256 does not match v2.1.16.'
}
Expand-Archive -LiteralPath $wxArchive -DestinationPath $work
Expand-Archive -LiteralPath $wcdbArchive -DestinationPath $work

$env:TEMP = $tmp
$env:TMP = $tmp
$env:GOTMPDIR = $tmp
$env:CGO_ENABLED = '0'
$env:GOOS = 'windows'
$env:GOARCH = 'amd64'

$wcdbSource = Join-Path $work 'wcdb-2.1.16'
$wcdbBuild = Join-Path $work 'wcdb-build'
$env:CL = "/experimental:deterministic /pathmap:`"$wcdbSource`"=wcdb"
& $CMake -S (Join-Path $wcdbSource 'src') -B $wcdbBuild -G 'Visual Studio 17 2022' -A x64 `
    '-DCMAKE_TRY_COMPILE_CONFIGURATION=Release' '-DCMAKE_POLICY_DEFAULT_CMP0141=NEW' `
    '-DCMAKE_MSVC_DEBUG_INFORMATION_FORMAT=' `
    '-DBUILD_SHARED_LIBS=ON' '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded' `
    '-DCMAKE_C_FLAGS=/DSQLITE_API=__declspec(dllexport)' '-DCMAKE_SHARED_LINKER_FLAGS=/Brepro /PDBALTPATH:%_PDB%'
if ($LASTEXITCODE -ne 0) { throw 'WCDB CMake configure failed.' }
& $CMake --build $wcdbBuild --config Release --target WCDB --parallel
if ($LASTEXITCODE -ne 0) { throw 'WCDB build failed.' }
$dll = Get-ChildItem $wcdbBuild -Recurse -File -Filter 'WCDB.dll' |
    Where-Object { $_.Directory.Name -eq 'Release' } | Select-Object -First 1
if (-not $dll) { throw 'WCDB.dll was not produced.' }
Copy-Item -LiteralPath $dll.FullName -Destination (Join-Path $bin 'libWCDB.dll') -Force

Push-Location (Join-Path $work "wx-cli-$commit")
try {
    & $Go build -trimpath -buildvcs=false -ldflags '-s -w' -o (Join-Path $bin 'wechat-cli.exe') ./cmd/wechat-cli
    if ($LASTEXITCODE -ne 0) { throw 'wx-cli build failed.' }
} finally {
    Pop-Location
}
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $bin 'wechat-cli.exe'), (Join-Path $bin 'libWCDB.dll')
