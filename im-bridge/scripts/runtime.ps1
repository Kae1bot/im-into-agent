function Get-BridgeRuntime {
    $command = Get-Command python.exe -CommandType Application -ErrorAction Stop
    $python = $command.Source
    $isSupported = & $python -I -B -c 'import sys; print(sys.prefix==sys.base_prefix and sys.version_info[:2]==(3,14) and sys.maxsize>2**32)'
    if ($LASTEXITCODE -ne 0 -or $isSupported -ne 'True') {
        throw 'AuRevior Skill requires an installed Windows x64 Python 3.14 runtime.'
    }
    $data = Join-Path $env:LOCALAPPDATA 'IM-into-Agent-AuRevior'
    @{
        Python = $python
        Config = Join-Path $data 'config.json'
    }
}
