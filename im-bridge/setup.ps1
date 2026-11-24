param(
    [switch]$CheckOnly,
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\scripts\runtime.ps1"
$runtime = Get-BridgeRuntime
$runner = "$PSScriptRoot\scripts\run-aurevior.py"
$version = & $runtime.Python -I -B $runner --version
if ($LASTEXITCODE -ne 0) { throw 'Could not start the bundled AuRevior dependencies.' }
if ($CheckOnly) {
    @{ok=$true; status='runtime_available'; backend=$version} | ConvertTo-Json -Compress
    return
}

$config = if ($ConfigPath) {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ConfigPath)
} else {
    Get-BridgeConfigPath $runtime
}
$response = & $runtime.Python -I -B $runner --check-config $config
$code = $LASTEXITCODE
if ($code -eq 0 -and $ConfigPath) {
    Save-BridgeConfigPath $runtime $config
}
$response
exit $code
