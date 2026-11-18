@echo off
rem Sync-Strata setup: checks what is already installed and installs only what is missing, old or broken.
rem The same one for the first install, a repair and a friend's PC. No administrator rights. Safe to run again.
rem Options are passed on (for example: setup.cmd -AppDir D:\SyncStrata  or  setup.cmd -ModelsDir D:\sync-bench\models).
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\installer.ps1" setup -Source "%~dp0feed" %*
set "SS_RC=%ERRORLEVEL%"
if not "%SS_NOPAUSE%"=="1" pause
exit /b %SS_RC%
