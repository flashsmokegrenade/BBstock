@echo off
title TradingAgents Launcher
cd /d "%~dp0"

echo ========================================================
echo         TradingAgents Analysis System
echo ========================================================
echo.

:: 1. Python check
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org
    echo Make sure to check "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b
)

:: 2. Setup environment package
echo [*] Checking package setup...
python -m pip install -e . >nul 2>&1

:: 3. Check .env file
if not exist ".env" (
    if exist ".env.enterprise.example" (
        copy ".env.enterprise.example" ".env" >nul
    ) else (
        echo OPENAI_API_KEY=> .env
    )
    echo [NOTICE] .env file created. Please enter your OPENAI_API_KEY in Notepad.
    start notepad .env
    echo Save and close Notepad, then press any key to continue.
    pause >nul
)

:: 4. Run Loop
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