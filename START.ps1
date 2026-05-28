# Social AI Assistant - Startup Script (PowerShell)
# This script starts both the backend and frontend servers

Write-Host ""
Write-Host "========================================"
Write-Host "Social AI Assistant - Starting..."
Write-Host "========================================"
Write-Host ""

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path

# Start backend in a new PowerShell window
Write-Host "Starting Backend (Flask) on http://127.0.0.1:5000..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptPath'; python run.py" -WindowStyle Normal

# Wait for backend to start
Start-Sleep -Seconds 3

# Start frontend in a new PowerShell window
Write-Host "Starting Frontend (React) on http://localhost:3000..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptPath\frontend'; npm run dev" -WindowStyle Normal

Write-Host ""
Write-Host "========================================"
Write-Host "Both servers are starting..."
Write-Host "Backend:  http://127.0.0.1:5000"
Write-Host "Frontend: http://localhost:3000"
Write-Host "========================================"
Write-Host ""
Write-Host "Close the terminal windows to stop the servers."
