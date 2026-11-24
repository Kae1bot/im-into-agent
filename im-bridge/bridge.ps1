$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
. "$PSScriptRoot\scripts\runtime.ps1"
$runtime = Get-BridgeRuntime
$arguments = @($args)
if ($arguments.Count -gt 0 -and $arguments[0] -in ('read','resolve')) {
    $arguments += @('--config', $runtime.Config)
}
& $runtime.Python -I -B "$PSScriptRoot\scripts\run-bridge.py" @arguments
exit $LASTEXITCODE
