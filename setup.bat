@echo off
rem First-time setup of Aadi Academic Video Creation on a developer machine (Windows). Safe to run again.
rem Needs: Python 3.12+, Node.js 20+, Docker Desktop (for PostgreSQL).
rem Result: database ready and the Aadi-Test company loaded (15 people with roles, a class and one APPROVED lesson, ready for "Make the video").
rem The video itself is made by the Video Engine (Media\ScriptToVideo); without it everything except "Make the video" works.
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python is not installed or not on PATH. Install Python 3.12 or newer from python.org and run again. & exit /b 1)
where node >nul 2>nul || (echo Node.js is not installed. Install Node.js 20 or newer and run again. & exit /b 1)
where docker >nul 2>nul || (echo Docker is not installed. Install Docker Desktop and run again. & exit /b 1)
docker info >nul 2>nul || (echo Docker is installed but not running. Start Docker Desktop, wait until it says running, and run again. & exit /b 1)

echo Starting PostgreSQL (port 15441)...
docker compose up -d postgres || exit /b 1
set /a tries=0
:wait
docker compose exec -T postgres pg_isready -U postgres >nul 2>nul && goto ready
set /a tries+=1
if %tries% GEQ 40 (echo The database did not become ready. Run "docker compose logs postgres". & exit /b 1)
timeout /t 2 /nobreak >nul
goto wait
:ready
docker compose exec -T postgres psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='academic_aadi_test'" | findstr 1 >nul || docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE academic_aadi_test" || exit /b 1

cd backend
if not exist .venv (
  echo Creating the Python environment...
  python -m venv .venv || exit /b 1
)
echo Installing packages...
.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements-dev.txt || exit /b 1

set DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:15441/academic_aadi_test
set AUTH_MODE=dev
set APP_ENV=development
set DEV_TENANT_ID=5ca1ab1e-aad1-4e57-8000-000000000001
set STORAGE_LOCAL_DIR=%~dp0backend\storage_aadi_test
echo Creating tables...
.venv\Scripts\python.exe -m app.migrate || exit /b 1
echo Loading the Aadi-Test company...
.venv\Scripts\python.exe -m app.seed_aadi_test || exit /b 1
cd ..

echo Installing the web app packages...
cd frontend
call npm install --no-audit --no-fund || exit /b 1
cd ..

echo.
echo Academic is ready. Start it with run.bat, then open http://localhost:5174
echo In development mode you act as an administrator of Aadi-Test (no sign-in). Sign-in with the 15 people happens through Aadi Identity (see identity\setup.bat).
endlocal
