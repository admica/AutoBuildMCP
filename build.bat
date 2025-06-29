@echo off
setlocal EnableDelayedExpansion

:: Check for Python 3.8 or higher
echo Checking for Python 3.8 or higher...
python --version > temp.txt 2>&1
set /p PYTHON_VERSION=<temp.txt
del temp.txt

echo Python version: %PYTHON_VERSION%
for /f "tokens=2 delims=. " %%a in ("%PYTHON_VERSION%") do (
    set MAJOR=%%a
)
for /f "tokens=3 delims=. " %%a in ("%PYTHON_VERSION%") do (
    set MINOR=%%a
)

if %MAJOR% LSS 3 (
    echo Error: Python version is less than 3. Please install Python 3.8 or higher.
    exit /b 1
)
if %MAJOR% EQU 3 if %MINOR% LSS 8 (
    echo Error: Python version is less than 3.8. Please install Python 3.8 or higher.
    exit /b 1
)
echo Found suitable Python version: %PYTHON_VERSION%

:: Remove old venv if exists
if exist venv (
    echo Removing existing 'venv' directory...
    rmdir /s /q venv
    echo Removed existing virtual environment.
)

:: Create new venv
echo Creating a new virtual environment...
python -m venv venv
if %ERRORLEVEL% NEQ 0 (
    echo Failed to create virtual environment.
    exit /b 1
)
echo Virtual environment created successfully.

:: Activate venv and install dependencies
call venv\Scripts\activate.bat
if exist requirements.txt (
    echo Installing dependencies from requirements.txt...
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to install dependencies. Check requirements.txt for conflicts or network issues.
        exit /b 1
    )
    echo Dependencies installed successfully.
) else (
    echo No requirements.txt found, skipping dependency installation.
)

echo Build environment setup complete and ready!
endlocal 