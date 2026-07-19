# Mansa Server
This repository is dedicated to storing all the server files related to the Mansa project, made in Python using mainly FastAPI, it contains all the structures necessary to run and deploy everything neeed for the project, including things like the [Brazillian Market Scraper](https://github.com/mansa-team/scraper-b3).

If you wanna know more about how the project is structured and how things on it, check the [documentation](https://github.com/mansa-team/server/tree/main/docs) for the project.
The server is structured in a way it can work natively at the machine (if you run an SQL databse locally or externally), but its recommended that you use the Docker Container for deployment.

## Run with Docker

```bash
# Build and start
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## Environment Setup

Create a `.env` file:

```env
#
#$ DATABASE
#
STOCKS_MYSQL_USER=user
STOCKS_MYSQL_PASSWORD=password
STOCKS_MYSQL_HOST=host
STOCKS_MYSQL_DATABASE=database

USER_MYSQL_USER=user
USER_MYSQL_PASSWORD=password
USER_MYSQL_HOST=db
USER_MYSQL_DATABASE=mansa_db

#
#$ USER
#
USER_ENABLED=TRUE
USER_HOST=localhost
USER_PORT=3200
JWT_SECRET_KEY=key
SESSION_SECRET_KEY=key
GOOGLE_CLIENT.ID=key
GOOGLE_CLIENT.SECRET=key
GOOGLE_REDIRECT.URI=http://localhost:3200/auth/callback

#
#$ STOCKS_API
#
STOCKSAPI_ENABLED=TRUE
STOCKSAPI_HOST=localhost
STOCKSAPI_PORT=3200
STOCKSAPI_KEY.SYSTEM=FALSE
STOCKSAPI_PRIVATE.KEY=key
STOCKSAPI_DEFAULT.QUOTA=5000
STOCKSAPI_QUOTA.RESETDAYS=30

#
#$ PROMETHEUS
#
PROMETHEUS_ENABLED=TRUE
PROMETHEUS_HOST=localhost
PROMETHEUS_PORT=3200
GEMINI_API.KEY=key
SEARXNG_URL=http://searxng:8888
FORGEVM_URL=http://forgevm:7423
SANDBOX_IMAGE=sandbox-python:latest
SANDBOX_MEMORY=512
SANDBOX_CPU=1
SANDBOX_TTL=5

#
#$ SCRAPER
#
SCRAPER_ENABLED=TRUE
SCRAPER_SCHEDULER=17:52 # Example: 18:30;18:45;19:00
JSON_EXPORT=TRUE
MYSQL_EXPORT=FALSE
MAX_WORKERS=40

#
#$ DISCORD (LOGGING)
#
DISCORD_ENABLED=FALSE
DISCORD_WEBHOOK_URL=url
```

## Health Check

```bash
curl http://localhost:3200/health
```

## License

Mansa Team's MODIFIED GPL 3.0 License. See LICENSE for details.
