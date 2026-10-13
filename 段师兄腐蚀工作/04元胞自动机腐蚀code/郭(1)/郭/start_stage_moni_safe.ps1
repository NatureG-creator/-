$ErrorActionPreference = "Stop"

$matlabExe = "E:\learning APP\MATLAB.R2026a\bin\win64\MATLAB.exe"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startupLog = Join-Path $scriptDir "matlab_startup_safe.log"
$runCommand = "try, cd('$scriptDir'); run_stage_moni_direct; disp('SAFE RUN FINISHED. Results are saved in outputs_matlab.'); catch ME, disp(getReport(ME,'extended','hyperlinks','off')); rethrow(ME); end"

Write-Host "Starting MATLAB safe run..."
Write-Host "MATLAB: $matlabExe"
Write-Host "Script: $scriptDir\run_stage_moni_direct.m"
Write-Host "Startup log: $startupLog"

if (-not (Test-Path -LiteralPath $matlabExe)) {
    throw "MATLAB executable not found: $matlabExe"
}

if (-not (Test-Path -LiteralPath (Join-Path $scriptDir "run_stage_moni_direct.m"))) {
    throw "run_stage_moni_direct.m not found in: $scriptDir"
}

& $matlabExe -batch $runCommand -logfile $startupLog
Write-Host "MATLAB exit code: $LASTEXITCODE"
