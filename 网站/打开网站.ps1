$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
    (Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe')
)
$pythonCandidates += @(Get-ChildItem -LiteralPath "$env:LOCALAPPDATA\Programs\Python" -Filter python.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') {
    $pythonCandidates += $pythonCommand.Source
}
$chosenPython = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $chosenPython) { throw '没有找到Python。请安装Python并按README安装依赖。' }
& $chosenPython (Join-Path $PSScriptRoot 'launch.py')
if ($LASTEXITCODE -ne 0) { throw '启动失败，请查看上面的中文提示。' }
