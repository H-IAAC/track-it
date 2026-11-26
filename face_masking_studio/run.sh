#!/usr/bin/env bash
set -euo pipefail

# Ensure script runs from the face_masking_studio folder
cd "$(dirname "$0")"

GLOBAL_VENV="../.venv"
LOCAL_VENV=".venv"

# Check if global .venv exists in toolkit root
if [ -f "$GLOBAL_VENV/bin/activate" ]; then
    echo "Using global virtual environment ($GLOBAL_VENV)..."
    source "$GLOBAL_VENV/bin/activate"
else
    echo "Global virtual environment not found."
    
    # Create local .venv if it does not exist
    if [ ! -d "$LOCAL_VENV" ]; then
        echo "Creating local virtual environment in face_masking_studio/$LOCAL_VENV..."
        python3 -m venv "$LOCAL_VENV"
    fi
    
    echo "Using local virtual environment ($LOCAL_VENV)..."
    source "$LOCAL_VENV/bin/activate"
    
    echo "Upgrading pip and installing backend dependencies..."
    pip install --upgrade pip
    
    # Install uvicorn to run the application
    pip install uvicorn
    
    if [ -f "backend/requirements.txt" ]; then
        pip install -r backend/requirements.txt
    else
        pip install fastapi "uvicorn[standard]" numpy onnxruntime pydantic opencv-python
    fi
fi

echo "Starting Face Masking Studio backend..."
cd backend
exec uvicorn main:app --host 127.0.0.1 --port 8000 --ws websockets
