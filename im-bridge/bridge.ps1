$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\scripts\runtime.ps1"
$runtime = Get-BridgeRuntime
$commandArgs = @($args)
if ($commandArgs.Count -gt 0 -and $commandArgs[0] -in @('read', 'resolve') -and
    '--help' -notin $commandArgs -and '-h' -notin $commandArgs) {
    if (-not (Test-Path -LiteralPath $runtime.Cli -PathType Leaf) -or
        -not (Test-Path -LiteralPath $runtime.Wcdb -PathType Leaf)) {
        throw 'Windows binaries are missing. Install the Windows Skill ZIP.'
    }
    if (-not (Test-Path -LiteralPath $runtime.Config -PathType Leaf)) {
        Write-Output '{"ok":false,"error":{"code":"key_missing","message":"Log in to Windows WeChat and run setup.ps1 before the first read."}}'
        exit 3
    }
    $commandArgs += @(
        '--cli', $runtime.Cli, '--wcdb-lib', $runtime.Wcdb,
        '--config', $runtime.Config, '--state-dir', $runtime.State
    )
}
& $runtime.Python -B "$PSScriptRoot\scripts\run-bridge.py" @commandArgs
exit $LASTEXITCODE
