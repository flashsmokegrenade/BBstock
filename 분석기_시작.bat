@echo off
chcp 65001 > nul
cd /d "%~dp0"

rem [경로 강제 고정] 파이썬이 무조건 현재 폴더의 최신 코드를 읽도록 만듭니다.
set PYTHONPATH=%~dp0
set PYTHONIOENCODING=utf-8

rem 1. 미국 주식 티커 입력 받기
set /p ticker="🔍 분석할 주식 티커를 입력하세요 (예: TSLA, AAPL, NVDA): "

rem 2. 오늘 날짜(YYYY-MM-DD) 자동 추출
for /f "tokens=*" %%i in ('python -c "from datetime import datetime; print(datetime.now().strftime('%%Y-%%m-%%d'))"') do set TODAY=%%i

echo.
echo [INFO] 프로그램 실시간 구동 시작합니다...
echo ---------------------------------------------------------
echo 🚀 분석을 시작합니다... [종목: %ticker% ^| 기준 날짜: %TODAY%]
echo ---------------------------------------------------------
echo.

rem 3. 오늘 날짜(%TODAY%)로 파이썬 실행
python main.py --ticker %ticker% --date %TODAY% --models gpt-4o-mini --rounds 2

echo ---------------------------------------------------------
echo 분석이 모두 완료되었습니다.
pause