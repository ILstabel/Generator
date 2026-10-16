@echo off
setlocal
title Chronic Pain / Opioid Risk Generator
cd /d "%~dp0app"
set "PY=%~dp0python\python.exe"
set "PORT=8765"
set "URL=http://localhost:%PORT%"

if not exist "%PY%" (
    echo The python folder is missing. Unzip the whole Generator folder before starting.
    pause
    exit /b 1
)

netstat -an | find ":%PORT% " | find "LISTENING" >nul
if not errorlevel 1 (
    echo The Generator is already running. Opening %URL%
    start "" "%URL%"
    exit /b 0
)

echo Starting the Chronic Pain / Opioid Risk Generator...
echo Your browser will open at %URL%
echo.
echo Keep this window open while using the app. Close it to stop the app.
echo.
rem Open the browser once the server has had a few seconds to start.
start "" /b cmd /c "ping -n 7 127.0.0.1 >nul & start "" "%URL%""
"%PY%" -m streamlit run app.py --server.address localhost --server.port %PORT% --server.headless true --browser.gatherUsageStats false --server.fileWatcherType none
echo.
echo The app has stopped.
pause
