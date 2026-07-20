#!/bin/bash
set -e

cd "$(dirname "$0")"

# Create .env from example if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it to set DEEPSEEK_API_KEY"
fi

# Create venv if not exists
if [ ! -d venv ]; then
    python3 -m venv venv
    echo "Created virtual environment"
fi

source venv/bin/activate

# Install dependencies
pip install -q -r requirements.txt

# Ensure data dirs exist
mkdir -p uploads exports data

# Copy .env to backend for local imports
cp .env backend/.env

echo ""
echo "=== Travel Content Factory ==="
echo "Starting at http://localhost:8000"
echo ""

cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
