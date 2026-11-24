param(
    [switch]$CheckOnly,
    [string]$PackagePath
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\scripts\runtime.ps1"
$runtime = Get-BridgeRuntime

if ($PackagePath) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $PackagePath).Path)
    try {
        $entries = foreach ($name in 'wechat-cli.exe', 'libWCDB.dll') {
            $matchesInZip = @($archive.Entries | Where-Object Name -eq $name)
            if ($matchesInZip.Count -ne 1) { throw "Expected one $name in the archive." }
            $matchesInZip[0]
        }
        $bin = Join-Path $runtime.Data 'bin'
        New-Item -ItemType Directory -Path $bin -Force | Out-Null
        foreach ($entry in $entries) {
            [IO.Compression.ZipFileExtensions]::ExtractToFile(
                $entry, (Join-Path $bin $entry.Name), $true
            )
        }
    } finally {
        $archive.Dispose()
    }
    $runtime = Get-BridgeRuntime
}

if (-not (Test-Path -LiteralPath $runtime.Cli -PathType Leaf) -or
    -not (Test-Path -LiteralPath $runtime.Wcdb -PathType Leaf)) {
    throw 'Windows binaries are missing. Install the Windows Skill ZIP.'
}

& $runtime.Python -B -c 'import ctypes, sys; ctypes.WinDLL(sys.argv[1]); print(sys.version.split()[0])' $runtime.Wcdb
if ($LASTEXITCODE -ne 0) { throw 'Could not start Python or load libWCDB.dll.' }
& $runtime.Cli version
if ($LASTEXITCODE -ne 0) { throw 'Could not start wechat-cli.exe.' }
if ($CheckOnly) { return }

New-Item -ItemType Directory -Path $runtime.Data -Force | Out-Null
Get-ChildItem Env: | Where-Object Name -Match '^(WECHAT_CLI_|WX_MCP_)' | ForEach-Object {
    Remove-Item -LiteralPath "Env:$($_.Name)"
}
$env:WECHAT_CLI_CONFIG = $runtime.Config
$env:WECHAT_CLI_STATE_DIR = $runtime.State
$env:WECHAT_CLI_WCDB_LIB = $runtime.Wcdb
$env:WECHAT_CLI_STRICT_READ_ONLY = '0'

& $runtime.Cli cache refresh --force | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'WeChat initialization failed. Log in to the Windows WeChat desktop app and retry.'
}
$statusJson = & $runtime.Cli status
if ($LASTEXITCODE -ne 0) { throw 'Could not verify local WeChat readiness.' }
$status = ($statusJson -join "`n") | ConvertFrom-Json
if (-not $status.ok -or -not $status.data.live_read_ok) {
    throw 'WeChat is not ready for local reads. Verify that WeChat is logged in and retry setup.'
}
Write-Output 'WeChat is ready for local reads.'
