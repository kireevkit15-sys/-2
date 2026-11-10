@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 goto bad_folder
if not exist "%~dp0launcher.py" goto incomplete
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto use_python
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto use_python3
echo Python 3.10+ was not found. Install Python from https://www.python.org/downloads/
echo Enable Python Launcher or Add Python to PATH during installation.
goto failed
:use_py
py -3 -X utf8 "%~dp0launcher.py"
goto finished
:use_python
python -X utf8 "%~dp0launcher.py"
goto finished
:use_python3
python3 -X utf8 "%~dp0launcher.py"
goto finished
:bad_folder
echo Cannot open the project folder. Extract the complete ZIP to a writable local folder.
goto failed
:incomplete
echo Incomplete project folder. Right-click the ZIP and choose Extract All.
echo Run start.bat from the extracted folder, NOT from inside the ZIP.
goto failed
:finished
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Startup failed. See the message above and data\startup.log if available.
pause
exit /b 1
