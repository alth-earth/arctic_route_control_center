@echo off
setlocal

rem Thin wrapper for teammates who prefer cmd.exe. The PowerShell script owns
rem all checks and arguments; this file must not contain credentials or paths.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-windows.ps1" %*
set "exit_code=%ERRORLEVEL%"

endlocal & exit /b %exit_code%
