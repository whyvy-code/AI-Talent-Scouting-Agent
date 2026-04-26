@echo off
setlocal

cd /d "%~dp0"

set "SCRIPT_PATH=%~dp0ai_talent_scouting_gemini_clean.py"
set "REQUIREMENTS_PATH=%~dp0requirements.txt"

if not exist "%SCRIPT_PATH%" (
  echo [ERROR] Script not found:
  echo %SCRIPT_PATH%
  pause
  exit /b 1
)

echo Installing/updating required packages...
py -m pip install --upgrade pip >nul 2>&1
if exist "%REQUIREMENTS_PATH%" (
  py -m pip install -r "%REQUIREMENTS_PATH%"
) else (
  py -m pip install streamlit google-genai pypdf
)
if errorlevel 1 (
  echo [ERROR] Package installation failed.
  pause
  exit /b 1
)

echo.
echo Starting app...
echo Gemini key can be entered in the Streamlit UI at launch.
echo If no key is entered, fallback mode will be used.
echo Open this URL if browser does not open automatically:
echo http://localhost:8501
echo.

py -m streamlit run "%SCRIPT_PATH%"

echo.
echo App stopped.
pause
