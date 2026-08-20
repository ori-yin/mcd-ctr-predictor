@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==============================
echo   MCD CTR Predictor - Launch
echo ==============================
echo.

:: ========== Check Python ==========
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.11+
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER%
echo.

:: ========== Create venv ==========
if not exist "venv\Scripts\activate.bat" (
    echo [1/3] Creating virtual environment...
    python -m venv --system-site-packages venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv
        pause
        exit /b 1
    )
    echo       Done!
) else (
    echo [1/3] venv already exists, skipping
)
echo.

:: Activate venv
call venv\Scripts\activate.bat

:: ========== Check dependencies ==========
echo [2/3] Checking dependencies...

set NEED_INSTALL=0

python -c "import streamlit"   >nul 2>&1 || (echo       [X] streamlit   missing & set NEED_INSTALL=1)
python -c "import pandas"      >nul 2>&1 || (echo       [X] pandas      missing & set NEED_INSTALL=1)
python -c "import openpyxl"    >nul 2>&1 || (echo       [X] openpyxl    missing & set NEED_INSTALL=1)
python -c "import openai"      >nul 2>&1 || (echo       [X] openai      missing & set NEED_INSTALL=1)
python -c "import anthropic"   >nul 2>&1 || (echo       [X] anthropic   missing & set NEED_INSTALL=1)

if %NEED_INSTALL%==0 (
    echo       All dependencies OK, skipping install
    goto :launch
)

echo.
echo       Installing missing packages (CN mirror)...
echo.
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
if %errorlevel% neq 0 (
    echo.
    echo [!] Aliyun mirror failed, trying Tsinghua mirror...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/ --trusted-host pypi.tuna.tsinghua.edu.cn
)
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Install failed. Check your network.
    pause
    exit /b 1
)
echo.
echo       Install done!

:: ========== Launch ==========
:launch
echo.
echo ==============================
echo   Starting... browser will open
echo   URL: http://localhost:8501
echo   Close this window to stop
echo ==============================
echo.
streamlit run ctr_predictor.py
pause