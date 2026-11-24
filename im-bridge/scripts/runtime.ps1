function Get-BridgeRuntime {
    $root = Split-Path -Parent $PSScriptRoot
    $data = Join-Path $env:LOCALAPPDATA 'IM-into-Agent'
    $bin = Join-Path $root 'bin'
    if (-not (Test-Path -LiteralPath (Join-Path $bin 'wechat-cli.exe') -PathType Leaf)) {
        $bin = Join-Path $data 'bin'
    }
    $python = Join-Path $root 'python\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        $command = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue
        if (-not $command) { throw 'Install the Windows Skill ZIP, which includes Python.' }
        $python = $command.Source
    }
    @{
        Root = $root
        Python = $python
        Cli = Join-Path $bin 'wechat-cli.exe'
        Wcdb = Join-Path $bin 'libWCDB.dll'
        Data = $data
        Config = Join-Path $data 'config.json'
        State = Join-Path $data 'state'
    }
}
