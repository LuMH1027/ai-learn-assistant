@echo off
setlocal
cd /d "%~dp0"

where node >nul 2>nul || (
  echo [ERROR] Node.js is required. Install Node.js 20.19+ or 22.12+.
  exit /b 1
)
where npm >nul 2>nul || (
  echo [ERROR] npm is required.
  exit /b 1
)

node -e "const [a,b]=process.versions.node.split('.').map(Number);if(!((a===20&&b>=19)||(a>=22&&(a>22||b>=12)))){console.error('[ERROR] Node.js 20.19+ or 22.12+ is required.');process.exit(1)}"
if errorlevel 1 exit /b 1

set "PYTHON_CMD="
where py >nul 2>nul && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  where python >nul 2>nul || (
    echo [ERROR] Python 3.9+ is required.
    exit /b 1
  )
  set "PYTHON_CMD=python"
)
%PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.9+ is required.
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo Installing frontend dependencies...
  npm ci --prefix frontend
  if errorlevel 1 exit /b 1
)

echo Building Vue frontend...
npm run build --prefix frontend
if errorlevel 1 exit /b 1

echo Starting Local Course Agent at http://127.0.0.1:8000
%PYTHON_CMD% run.py
