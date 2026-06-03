@echo off
REM Social AI Assistant - Startup Script
REM This script starts both the backend and frontend servers

echo.
echo ========================================
echo Social AI Assistant - Starting...
echo ========================================
echo.

REM Start backend in a new window
echo Starting Backend (Flask) on http://127.0.0.1:5000...
start "Backend - Flask" cmd /k "cd /d %~dp0 && python run.py"

REM Wait a moment for backend to start
timeout /t 3 /nobreak

REM Start frontend in a new window
echo Starting Frontend (React) on http://localhost:3000...
start "Frontend - React" cmd /k "cd /d %~dp0\frontend && npm run dev"

echo.
echo ========================================
echo Both servers are starting...
echo Backend: http://127.0.0.1:5000
echo Frontend: http://localhost:3000
echo ========================================
echo.
echo Press Ctrl+C in each window to stop the servers.
pause
