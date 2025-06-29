@echo off
setlocal

:: Check for venv existence
if not exist venv\Scripts\activate.bat (
    echo Virtual environment not found at venv\Scripts\activate.bat
    echo Please run build.bat first to set up the environment.
    exit /b 1
)

:: Activate venv
call venv\Scripts\activate.bat

:: Run the server
python server.py

endlocal 