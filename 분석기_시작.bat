@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo         TradingAgents Analysis System
echo ========================================================
echo.

:: Python Check
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b
)

:: Package Connect
echo [*] Checking package setup...
python -m pip install -e . >nul 2>&1

:RUN_LOOP
echo.
echo ---------------------------------------------------------
set /p TICKER="Enter Stock Ticker (e.g. TSLA, AAPL, NVDA): "
if "%TICKER%"=="" goto RUN_LOOP

echo.
echo [INFO] Running TradingAgents for %TICKER%...
echo ---------------------------------------------------------
python main.py --ticker %TICKER%
echo ---------------------------------------------------------
echo [INFO] Analysis completed.
echo.

set /p AGAIN="Do you want to analyze another stock? (Y/N): "
if /i "%AGAIN%"=="Y" goto RUN_LOOP

echo Closing program...
pause