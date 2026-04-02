@echo off
REM setup.bat - Infrastructure Setup Script for Mansa Server (Windows)

echo [Mansa] Starting Infrastructure Setup...

REM 1. Check for .env file
if not exist .env (
    echo [Mansa] .env file not found. Creating default...
    (
        echo MYSQL_USER=user
        echo MYSQL_PASSWORD=password
        echo MYSQL_HOST=db-dev
        echo MYSQL_DATABASE=mansa_db
        echo DEBUG_MODE=true
    ) > .env
)

REM 2. Start the Docker containers
echo [Mansa] Starting Docker containers...
docker-compose up -d

REM 3. Wait for MySQL to be ready
echo [Mansa] Waiting for MySQL to initialize (this may take a moment)...
:wait_mysql
docker-compose exec db-dev mysqladmin ping -h"localhost" -u"user" -p"password" --silent >nul 2>&1
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_mysql
)

REM 4. Run Alembic Migrations
echo [Mansa] Running database migrations...
docker-compose exec api alembic upgrade head

echo [Mansa] Setup complete!
echo [Mansa] API is running at: http://localhost:8000
pause
