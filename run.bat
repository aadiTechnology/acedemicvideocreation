@echo off
rem Starts Academic for development: the API on http://127.0.0.1:8100 and the web app on http://localhost:5174 (run setup.bat once first).
cd /d "%~dp0"
docker compose up -d postgres >nul 2>nul
set DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:15441/academic_aadi_test
set AUTH_MODE=dev
set APP_ENV=development
set DEV_TENANT_ID=5ca1ab1e-aad1-4e57-8000-000000000001
set STORAGE_LOCAL_DIR=%~dp0backend\storage_aadi_test
rem Optional: set VIDEO_ENGINE_URL and VIDEO_ENGINE_API_KEY (or the token settings) to make videos.
start "Academic API" /d "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8100 --reload"
cd frontend
call npm run dev
