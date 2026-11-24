param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\scripts\runtime.ps1"
$runtime = Get-BridgeRuntime
& $runtime.Python -I -B "$PSScriptRoot\scripts\run-aurevior.py" --version
if ($LASTEXITCODE -ne 0) { throw 'Could not start the bundled AuRevior dependencies.' }
if ($CheckOnly) { return }
if (-not (Test-Path -LiteralPath $runtime.Config -PathType Leaf)) {
    @{ok=$false; error=@{code='key_missing'; message='No authorized AuRevior configuration was provisioned.'}} |
        ConvertTo-Json -Compress
    exit 3
}
@{ok=$true; status='runtime_available'; config_present=$true} | ConvertTo-Json -Compress
