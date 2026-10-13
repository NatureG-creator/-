@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_matlab_check.ps1"

echo.
echo Check outputs_matlab\matlab_startup_check.txt and matlab_startup_check.log.
pause
