@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Ошибка: не найдено виртуальное окружение .venv
    echo Ожидается файл: %~dp0.venv\Scripts\activate.bat
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo === Расписание на следующую неделю ===
python spbu_schedule.py --week next

echo.
pause