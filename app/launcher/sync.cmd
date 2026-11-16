@echo off
rem Sync CLI. Usage: sync up ^| down ^| status ^| settings ^| gui-url ^| api ^| doctor ^| chat
rem Uses the bundled Python (..\python\python.exe) when installed; otherwise py -3.
if exist "%~dp0..\python\python.exe" (
  "%~dp0..\python\python.exe" -s -X utf8 "%~dp0sync.py" %*
) else (
  py -3 -X utf8 "%~dp0sync.py" %*
)
exit /b %ERRORLEVEL%
