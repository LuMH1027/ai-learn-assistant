@echo off
setlocal
cd /d "%~dp0"

where node >nul 2>nul || (
  echo [ERROR] Node.js 20.19+ or 22.12+ is required before installing project dependencies.
  exit /b 1
)
where npm >nul 2>nul || (
  echo [ERROR] npm is required before installing project dependencies.
  exit /b 1
)

node -e "const [a,b]=process.versions.node.split('.').map(Number);if(!((a===20&&b>=19)||(a>=22&&(a>22||b>=12)))){console.error('[ERROR] Node.js 20.19+ or 22.12+ is required.');process.exit(1)}"
if errorlevel 1 exit /b 1

set "SYSTEM_PYTHON="
where py >nul 2>nul && set "SYSTEM_PYTHON=py -3"
if not defined SYSTEM_PYTHON (
  where python >nul 2>nul || (
    echo [ERROR] Python 3.9+ is required before installing project dependencies.
    exit /b 1
  )
  set "SYSTEM_PYTHON=python"
)

%SYSTEM_PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.9+ is required.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment in .venv...
  %SYSTEM_PYTHON% -m venv .venv
  if errorlevel 1 exit /b 1
)

if exist ".venv\.course-agent-deps-ready" del /q ".venv\.course-agent-deps-ready"

echo Installing Python dependencies from requirements.txt...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo Installing locked frontend dependencies from frontend\package-lock.json...
call npm ci --prefix frontend --include=dev
if errorlevel 1 exit /b 1

type nul > ".venv\.course-agent-deps-ready"

echo All project dependencies are installed. Run start.bat to start the application.
