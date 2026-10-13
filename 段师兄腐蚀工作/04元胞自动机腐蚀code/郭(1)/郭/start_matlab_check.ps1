$ErrorActionPreference = "Stop"

$matlabExe = "E:\learning APP\MATLAB.R2026a\bin\win64\MATLAB.exe"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startupLog = Join-Path $scriptDir "matlab_startup_check.log"
$runCommand = "try, cd('$scriptDir'); matlab_startup_check; catch ME, disp(getReport(ME,'extended','hyperlinks','off')); rethrow(ME); end"

Write-Host "Running MATLAB startup check..."
Write-Host "MATLAB: $matlabExe"
Write-Host "Script: $scriptDir\matlab_startup_check.m"
Write-Host "Log: $startupLog"

& $matlabExe -batch $runCommand -logfile $startupLog
Write-Host "MATLAB exit code: $LASTEXITCODE"
