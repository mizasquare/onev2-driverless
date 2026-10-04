@echo off
rem Double-click this. It finds Python, installs the two packages the tools need into a
rem private folder inside this one, and opens the menu. It does not need Administrator.
rem Nothing here writes to the ONE on its own -- the menu asks first.
title Apogee ONE firmware patch
cd /d "%~dp0"

set VENV=%~dp0.venv
set VPY=%VENV%\Scripts\python.exe

echo.
echo   Apogee ONE -- driverless firmware patch
echo   =======================================
echo.

if exist "%VPY%" goto :haveenv

rem ---------------------------------------------------------------- find a Python
set PY=
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set PY=py -3
if defined PY goto :makeenv
python -c "import sys" >nul 2>&1
if not errorlevel 1 set PY=python
if defined PY goto :makeenv

echo   Python is not installed on this computer, and the tools here are
echo   written in Python. It is a free download from python.org and takes
echo   about a minute.
echo.
where winget >nul 2>&1
if errorlevel 1 goto :nowinget

echo   Windows can install it for you. Nothing else on your computer
echo   changes.
echo.
set /p ANS=  Install Python now? [Y/n]
if /i "%ANS%"=="n" goto :manualpy

echo.
echo   Installing. Windows may ask you to approve it.
echo.
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements

py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set PY=py -3
if defined PY goto :makeenv

echo.
echo   Python is installed now, but this window started before it existed
echo   and cannot see it yet.
echo.
echo   Close this window and double-click PATCH-ME-WINDOWS.bat again.
echo.
pause
exit /b 0

:nowinget
echo   This copy of Windows has no winget, so install Python by hand.
:manualpy
echo.
echo   1. Go to  https://www.python.org/downloads/
echo   2. Download Python for Windows and run the installer.
echo   3. On the first installer screen, tick "Add python.exe to PATH".
echo   4. Close this window and double-click PATCH-ME-WINDOWS.bat again.
echo.
pause
exit /b 1

rem ---------------------------------------------------------------- private env
:makeenv
echo   Setting up, once. This makes a folder called .venv inside this one
echo   and puts two USB packages in it. Your system Python is left alone.
echo.
%PY% -m venv "%VENV%"
if not exist "%VPY%" goto :envfailed

"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
echo   Installing pyusb and libusb-package...
"%VPY%" -m pip install --quiet --disable-pip-version-check pyusb libusb-package
if errorlevel 1 goto :pipfailed

echo   Installing sounddevice and numpy, used by the test...
"%VPY%" -m pip install --quiet --disable-pip-version-check sounddevice numpy
echo.
echo   Ready.
goto :haveenv

:envfailed
echo.
echo   Could not create the .venv folder. If this folder is inside OneDrive
echo   or on a network drive, copy the whole project somewhere local such as
echo   C:\onev2 and try again.
echo.
pause
exit /b 1

:pipfailed
echo.
echo   Could not download the USB packages. That is almost always no
echo   internet, or a company proxy blocking it. The two needed are
echo   pyusb and libusb-package.
echo.
pause
exit /b 1

rem ---------------------------------------------------------------- go
:haveenv
"%VPY%" "%~dp0tools\menu.py"
echo.
pause
