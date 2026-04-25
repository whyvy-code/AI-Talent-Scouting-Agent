@echo off
setlocal

cd /d "%~dp0"

set "SCRIPT_PATH=C:\Users\Vikas Yadav\Downloads\ai_talent_scouting_gemini_clean.py"

if not exist "%SCRIPT_PATH%" (
  echo [ERROR] Script not found:
  echo %SCRIPT_PATH%
  pause
  exit /b 1
)

echo Installing/updating required packages...
py -m pip install --upgrade pip >nul 2>&1
py -m pip install streamlit google-genai pypdf
if errorlevel 1 (
  echo [ERROR] Package installation failed.
  pause
  exit /b 1
)

if "%GEMINI_API_KEY%"=="" (
  echo.
  echo Gemini key is optional now.
  set /p GEMINI_API_KEY=Enter GEMINI_API_KEY or press Enter for fallback mode: 
)

echo.
echo Starting app...
if "%GEMINI_API_KEY%"=="" (
  echo Running without Gemini key. Non-LLM fallback mode will be used if needed.
) else (
  echo Gemini key detected. App will run startup model check automatically.
)
echo Open this URL if browser does not open automatically:
echo http://localhost:8501
echo.

py -m streamlit run "%SCRIPT_PATH%"

echo.
echo App stopped.
pause
