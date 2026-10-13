@echo off
setlocal
cd /d "%~dp0"
title SmearSight installer
echo.
echo  ==============================================
echo   SmearSight installer  (one time, needs internet)
echo  ==============================================
echo.

rem ---- 1. find a suitable Python (3.10 or newer) -------------------------------------
set "PY="
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo  [!] Python 3.10 or newer was not found.
  echo.
  echo      1. Go to https://www.python.org/downloads/  and download Python 3.12
  echo      2. Run the installer and TICK THE BOX "Add python.exe to PATH" on the first screen
  echo      3. Close this window and double-click install_windows.bat again
  echo.
  pause
  exit /b 1
)
echo  Using Python:  %PY%
%PY% --version
echo.

rem ---- 2. private environment ----------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo  Creating the private Python environment...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check

rem ---- 3. packages (about 1 to 2 GB, 5 to 20 minutes; retried automatically) ---------
echo  Installing packages. This is a big download, please keep this window open...
echo  (Nothing seems to happen for a few minutes while PyTorch downloads. That is normal.)
echo.
"%VPY%" -m pip install --prefer-binary --default-timeout=120 --log install_log.txt -r requirements.txt ^
 || "%VPY%" -m pip install --prefer-binary --default-timeout=120 --log install_log.txt -r requirements.txt ^
 || "%VPY%" -m pip install --prefer-binary --default-timeout=120 --log install_log.txt -r requirements.txt ^
 || goto :fail

"%VPY%" -c "import django, rest_framework, waitress, cv2, ultralytics" >nul 2>&1
if errorlevel 1 goto :fail

echo.
echo  ==============================================
echo   Installed. Starting SmearSight...
echo   Next time just double-click  start_windows.bat
echo  ==============================================
echo.
call start_windows.bat
exit /b 0

:fail
echo.
echo  [!] The installation did not finish.
echo.
echo      Common causes:
echo        - the internet dropped: run this file again, it continues where it stopped
echo        - antivirus or a hospital network blocks downloads: try a phone hotspot for the install
echo        - less than 3 GB free disk space
echo        - a very new Python: install Python 3.12 from python.org and delete the .venv folder
echo.
echo      If it still fails, send the last lines above, or the file install_log.txt, to whoever shared this app.
echo.
pause
exit /b 1
