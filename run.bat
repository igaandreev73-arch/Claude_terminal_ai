@echo off
chcp 65001 >nul
title Crypto Terminal

set PYTHONUTF8=1

echo ==========================================
echo   Crypto Terminal - starting
echo ==========================================
echo.

REM --- Copy .env if missing ---
if not exist .env (
    echo [WARN] .env not found, copying from .env.example...
    copy .env.example .env >nul
)

REM --- Kill previous backend if port 8765 is busy ---
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765 "') do (
    taskkill /F /PID %%a >nul 2>&1
)

REM --- Python backend in new window ---
echo [1/2] Starting Python backend...
start "Backend" cmd /k "python -X utf8 main.py"

REM --- Wait for backend to boot ---
timeout /t 3 /nobreak >nul

REM --- React UI in new window ---
echo [2/2] Starting React UI...
start "UI" cmd /k "cd ui\react-app && npm run dev"

echo.
echo ==========================================
echo   Backend:  ws://localhost:8765/ws
echo   UI:       http://localhost:5173
echo ==========================================
echo.
pause
