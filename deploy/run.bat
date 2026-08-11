@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo ============================================
echo  API Aggregation Platform - Windows Deploy
echo ============================================
echo.

echo [1/4] Clearing Python caches...
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
for /d /r %%d in (.pytest_cache) do @if exist "%%d" rd /s /q "%%d" 2>nul
for /d /r %%d in (.mypy_cache) do @if exist "%%d" rd /s /q "%%d" 2>nul
for /d /r %%d in (.ruff_cache) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q "*.pyc" 2>nul
if exist ".coverage" del /q ".coverage" 2>nul
echo       Done.

echo [2/4] Creating virtual environment (.venv)...
if exist ".venv\Scripts\python.exe" (
  echo       .venv already exists - reusing it.
) else (
  where py >nul 2>nul
  if %ERRORLEVEL%==0 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 (
    echo ERROR: Failed to create .venv. Is Python 3 installed and on PATH?
    exit /b 1
  )
  echo       Created .venv
)

echo [3/4] Installing dependencies...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: pip install failed.
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" (
    copy /y ".env.example" ".env" >nul
    echo       Created .env from .env.example
  )
)

echo [4/4] Starting API on http://127.0.0.1:8000 ...
echo       Admin:  http://127.0.0.1:8000/admin
echo       Docs:   http://127.0.0.1:8000/docs
echo       Press Ctrl+C to stop.
echo.
call ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

endlocal
