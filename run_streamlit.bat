@echo off
REM SEO-Content-Engine - Windows Startup Script

echo.
echo ====================================================
echo  SEO-Content-Engine - Streamlit POC
echo ====================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+ from python.org
    exit /b 1
)

echo Syncing dependencies with uv...
uv sync --quiet

if not exist .env (
    echo.
    echo Creating .env file...
    echo GROQ_API_KEY=your_key_here > .env
    echo.
    echo ⚠️  Please add your Groq API key to .env file
    echo    Get a free key from: https://console.groq.com
    echo.
)

echo.
echo Launching Streamlit app...
echo.
echo The app will open at: http://localhost:8501
echo.
pause

uv run streamlit run streamlit_app.py

pause
