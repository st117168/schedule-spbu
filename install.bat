@echo off
chcp 65001 >nul
title Установка зависимостей
cd /d "%~dp0"

echo ============================================
echo   Установка окружения
echo ============================================
echo.

REM ── Проверка Python ─────────────────────────
where python >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в PATH.
    echo Установите Python 3 и добавьте его в PATH.
    echo.
    pause
    exit /b 1
)

REM ── Создание .venv (если его нет) ───────────
if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать .venv.
        pause
        exit /b 1
    )
    echo .venv создано.
) else (
    echo .venv уже существует — пропускаю создание.
)

REM ── Активация ───────────────────────────────
call ".venv\Scripts\activate.bat"

REM ── Обновление pip ──────────────────────────
echo.
echo Обновляю pip...
python -m pip install --upgrade pip

REM ── Установка из requirements.txt ───────────
if not exist "requirements.txt" (
    echo.
    echo [ПРЕДУПРЕЖДЕНИЕ] Файл requirements.txt не найден.
    echo Устанавливаю базовый набор пакетов вручную...
    pip install flask pandas requests pillow openpyxl
) else (
    echo.
    echo Устанавливаю зависимости из requirements.txt...
    pip install -r requirements.txt
)

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить некоторые пакеты.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Готово! Можно запускать start_server.bat
echo ============================================
echo.
pause