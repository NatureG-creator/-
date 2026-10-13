@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_stage_moni_safe.ps1"

echo.
echo MATLAB window closed. Check outputs_matlab for .mat result and .log files.
pause
