$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $PSScriptRoot '.venv\Scripts\python.exe')
)
$pythonCandidates += @(Get-ChildItem -LiteralPath "$env:LOCALAPPDATA\Programs\Python" -Filter python.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') { $pythonCandidates += $pythonCommand.Source }
$chosenPython = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $chosenPython) { throw '未找到Python。' }
& $chosenPython -m backend.git_sync
if ($LASTEXITCODE -ne 0) { throw '同步失败，请查看Git提示。已提交的代码仍保留在本机，可再次同步。' }
