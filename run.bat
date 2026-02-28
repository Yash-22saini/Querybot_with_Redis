@echo off
echo Starting Nova AI Chat...
echo Open http://localhost:8000 in your browser
echo Press Ctrl+C to stop
uvicorn app:app --host localhost --port 8000 --reload