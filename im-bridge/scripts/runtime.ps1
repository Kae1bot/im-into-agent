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
        Data = $data
    }
}

function Get-BridgeConfigPath($runtime) {
    $selection = Join-Path $runtime.Data 'reader.json'
    if (Test-Path -LiteralPath $selection -PathType Leaf) {
        $config = (Get-Content -Raw -LiteralPath $selection | ConvertFrom-Json).config
        if ($config -isnot [string] -or -not [IO.Path]::IsPathRooted($config)) {
            throw 'The saved AuRevior configuration path is invalid.'
        }
        return $config
    }
    return (Join-Path $runtime.Data 'config.json')
}

function Save-BridgeConfigPath($runtime, [string]$config) {
    New-Item -ItemType Directory -Path $runtime.Data -Force | Out-Null
    $selection = Join-Path $runtime.Data 'reader.json'
    $temporary = Join-Path $runtime.Data ("reader-" + [guid]::NewGuid() + ".tmp")
    try {
        $json = @{ config = $config } | ConvertTo-Json -Compress
        [IO.File]::WriteAllText($temporary, $json, [Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath $selection -PathType Leaf) {
            [IO.File]::Replace($temporary, $selection, $null)
        } else {
            [IO.File]::Move($temporary, $selection)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) {
            Remove-Item -LiteralPath $temporary
        }
    }
}
