@echo off
chcp 65001 >nul
title Планировщик + СПбГУ
cd /d "%~dp0"

echo ============================================
echo   Планировщик + СПбГУ
echo ============================================
echo.

REM ── Проверка .venv ──────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo [ОШИБКА] Виртуальное окружение .venv не найдено.
    echo Сначала запустите install.bat для его создания.
    echo.
    pause
    exit /b 1
)

REM ── Активация .venv ─────────────────────────
call ".venv\Scripts\activate.bat"

REM ── Запуск сервера ──────────────────────────
echo Запускаю сервер на http://127.0.0.1:5000
echo Для остановки нажмите Ctrl+C или закройте окно.
echo.

REM Открываем браузер через 2 секунды после старта сервера
start "" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:5000"

python server.py

echo.
echo Сервер остановлен.
pause