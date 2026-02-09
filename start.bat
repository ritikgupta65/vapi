@echo off
echo Starting Speech-to-Speech AI System...
echo.

REM Check if .env exists
if not exist "backend\.env" (
    echo Creating .env from .env.example...
    copy "backend\.env.example" "backend\.env"
    echo Created backend/.env - Please edit it with your API keys!
    echo.
)

echo Starting backend server...
cd backend
start "Backend Server" cmd /k python main.py
cd ..

timeout /t 3 /nobreak > nul

echo Starting frontend...
cd frontend
start "Frontend Server" cmd /k npm run dev
cd ..

echo.
echo System started!
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
echo.
pause
