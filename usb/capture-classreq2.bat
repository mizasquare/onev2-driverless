@echo off
setlocal
echo [capture-classreq2] starting
REM ===========================================================================
REM  See the UAC2 class control requests on the wire.
REM
REM  RUN THIS IN AN ELEVATED (Administrator) cmd.exe. Starting an ETW session
REM  needs it; nothing else here does.
REM
REM  It traces Microsoft-Windows-USB-UCX, the provider that carries the 8-byte
REM  SETUP packets. Verified against an earlier capture of this device: the
REM  fid_URB_Setup_* fields live in UCX's URB_FUNCTION_CONTROL_TRANSFER_EX
REM  events. USBXHCI does NOT have them -- it only logs xHCI slot/endpoint/TRB
REM  activity, which is why the first attempt came back with zero setup packets.
REM
REM  Inside the window it runs exercise-classreq.py, which drives the device
REM  through ten numbered phases: clock retune at 44.1/48/96 kHz, each capture
REM  endpoint, the selector moved in both directions, and an exclusive-mode
REM  capture. Then it decodes the trace and prints the answer.
REM
REM  Everything the exerciser sends is a GET except the vendor 0x36 writes that
REM  move the input selector, and it restores Internal Mic with phantom power
REM  off when it finishes. Nothing is flashed.
REM
REM  Takes about a minute. Leaves these in resources\ :
REM    usbtrace-classreq.etl    the raw capture
REM    usbtrace-classreq.xml    the decoded capture (large, deletable)
REM    classreq-result.txt      the readable answer   <-- send me this one
REM ===========================================================================

set HERE=%~dp0
set HERE=%HERE:~0,-1%
set RES=%HERE%
if "%PY%"=="" set PY=python
set ETL=%RES%\usbtrace-classreq.etl
set XML=%RES%\usbtrace-classreq.xml
set SUM=%RES%\usbtrace-classreq-summary.txt
set PH=%RES%\usbtrace-classreq-phases.json
set RESULT=%RES%\classreq-result.txt
set SES=onereq2
set UCX={36da592d-e43a-4e28-af6f-4bc57c5a11e8}
REM UCX keywords 0x1C0 = HeadersBusTrace + PartialDataBusTrace + FullDataBusTrace
set KW=0x80000000000001C0

fltmc >nul 2>&1
if errorlevel 1 (
  echo.
  echo This window is NOT elevated. Right-click cmd.exe, "Run as administrator",
  echo and run this batch again. Nothing has been changed.
  goto :end
)

if not exist "%PY%" (
  echo Cannot find the project venv python at %PY%
  goto :end
)
if not exist "%HERE%\exercise-classreq.py" (
  echo Cannot find %HERE%\exercise-classreq.py
  goto :end
)

echo.
echo === clearing any leftover session and old output ===
logman stop %SES% -ets >nul 2>&1
logman stop onereq -ets >nul 2>&1
del "%ETL%" "%XML%" "%SUM%" "%PH%" "%RESULT%" >nul 2>&1

echo.
echo === starting the UCX capture ===
logman create trace %SES% -ets -o "%ETL%" -nb 64 256 -bs 128 -p "%UCX%" %KW% 0xff
if errorlevel 1 (
  echo.
  echo Could not start the trace session. If the error says the name is in use:
  echo    logman stop %SES% -ets
  goto :end
)

echo.
echo === driving the device through the phases, about 30 s, no sound is played ===
"%PY%" "%HERE%\exercise-classreq.py" %*
set EXERCISE=%errorlevel%

echo.
echo === stopping the capture ===
logman stop %SES% -ets
if not "%EXERCISE%"=="0" echo    NOTE: exerciser exit code %EXERCISE% - the trace may be partial.
for %%A in ("%ETL%") do echo    captured %%~zA bytes

echo.
echo === decoding, this is the slow part ===
tracerpt "%ETL%" -o "%XML%" -of XML -summary "%SUM%" -y
if errorlevel 1 (
  echo    tracerpt failed. The .etl is still there - tell me and I will decode it another way.
  goto :end
)
for %%A in ("%XML%") do echo    decoded to %%~zA bytes

echo.
echo === the answer ===
"%PY%" "%HERE%\parse-classreq.py" "%XML%" "%PH%" > "%RESULT%" 2>&1
type "%RESULT%"

echo.
echo ---------------------------------------------------------------------------
echo Saved to %RESULT%
echo Send me that file, or paste the output above.
echo The .xml is large and can be deleted once I have read the result.
echo ---------------------------------------------------------------------------

:end
endlocal
echo [capture-classreq2] done
pause
