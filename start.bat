@echo off
cd /d "%~dp0"
py -3 --version >nul 2>&1
if errorlevel 1 (
 echo Install Python 3.10+ from python.org first.
 pause
 exit /b 1
)
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --no-index --find-links vendor -r requirements.txt
if errorlevel 1 (
 pause
 exit /b 1
)
echo Open http://localhost:8000 on this computer.
echo Phone: use http://YOUR_COMPUTER_IP:8000 on the same Wi-Fi.
.venv\Scripts\python.exe app.py --host 0.0.0.0
pause
