#!/bin/bash
# SEO-Content-Engine - macOS/Linux Startup Script

echo ""
echo "===================================================="
echo "  SEO-Content-Engine - Streamlit POC"
echo "===================================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Please install Python 3.8+ from python.org"
    exit 1
fi

echo "Syncing dependencies with uv..."
uv sync --quiet

if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file..."
    echo "GROQ_API_KEY=your_key_here" > .env
    echo ""
    echo "⚠️  Please add your Groq API key to .env file"
    echo "   Get a free key from: https://console.groq.com"
    echo ""
fi

echo ""
echo "Launching Streamlit app..."
echo ""
echo "The app will open at: http://localhost:8501"
echo ""

uv run streamlit run streamlit_app.py
