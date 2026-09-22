@echo off
REM Rebuild and restart the orchestrator container with fixes

echo Stopping containers...
docker-compose stop orchestrator

echo Rebuilding orchestrator...
docker-compose build orchestrator

echo Starting containers...
docker-compose up -d

echo Waiting for services to be ready...
timeout /t 5 /nobreak >nul

echo Checking orchestrator logs...
docker-compose logs --tail=20 orchestrator

echo.
echo Done! Test with:
echo curl http://localhost:8000/health
echo curl http://localhost:8000/export_csv

