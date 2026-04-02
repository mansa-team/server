#!/bin/bash
# setup.sh - Infrastructure Setup Script for Mansa Server

echo "🚀 Starting Mansa Infrastructure Setup..."

# 1. Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env 2>/dev/null || echo "MYSQL_USER=user
MYSQL_PASSWORD=password
MYSQL_HOST=db-dev
MYSQL_DATABASE=mansa_db
DEBUG_MODE=true" > .env
fi

# 2. Start the Docker containers
echo "📦 Starting Docker containers (Database, API, Scraper)..."
docker-compose up -d

# 3. Wait for MySQL to be ready
echo "⏳ Waiting for MySQL to initialize..."
until docker-compose exec db-dev mysqladmin ping -h"localhost" -u"user" -p"password" --silent; do
    sleep 2
done

# 4. Run Alembic Migrations
echo "🗄️  Running database migrations..."
docker-compose exec api alembic upgrade head

echo "✅ Setup complete!"
echo "🌐 API is running at: http://localhost:8000"
echo "📊 Scraper is running in the background."
