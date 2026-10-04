@echo off
setlocal
title UAD 3.6 Bridge - HUD

REM One click: put the bridge's panel on whatever UAD 3.6 report is open in
REM TOTAL, and keep it there.  It waits if TOTAL is not running yet, attaches
REM to each 3.6 report as it opens -- including one opened after another is
REM closed -- and refreshes itself every couple of seconds, so the panel is
REM always showing the report actually in front of you.
REM
REM Close this window to stop watching.  Panels already installed stay put.

cd /d "%~dp0"

set PY=
for %%P in (py.exe) do if not defined PY if not "%%~$PATH:P"=="" set PY=py -3
for %%P in (python.exe) do if not defined PY if not "%%~$PATH:P"=="" set PY=python
if not defined PY (
  echo Python 3.11 or newer is needed and was not found on PATH.
  echo Install it from python.org, then run this again.
  pause
  exit /b 1
)

echo Starting the UAD 3.6 bridge HUD.
echo.
echo   * Open a UAD 3.6 report in TOTAL - the panel appears on it by itself.
echo   * Use the panel to bring in an XML file.
echo   * Leave this window open; closing it stops the watcher.
echo.

%PY% bridge_main.py hud --watch
set CODE=%ERRORLEVEL%

echo.
if not "%CODE%"=="0" (
  echo The watcher stopped with code %CODE%.
  echo If TOTAL was not running, start it and run this again.
)
pause
