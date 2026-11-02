@echo off
setlocal
cd /d "%~dp0"

python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

python -m pip install pyinstaller
if errorlevel 1 exit /b 1

python -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name HarmonicMix ^
  --icon HarmonicMix.ico ^
  --add-data "HarmonicMix.ico;." ^
  --collect-all customtkinter ^
  --collect-all mutagen ^
  app.py
if errorlevel 1 exit /b 1

echo.
echo Executable created: dist\HarmonicMix.exe
pause
