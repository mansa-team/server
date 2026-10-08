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

#
#$ ORUNMILA
#
ORUNMILA_ENABLED=TRUE
ORUNMILA_HOST=localhost
ORUNMILA_PORT=3200
GEMINI_API.KEY=key
SEARXNG_URL=http://searxng:8888
FORGEVM_URL=http://forgevm:7423
FORGEVM_API_TOKEN=key


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

#
#$ CACHE
#
REDIS_URL=redis://redis:6379 # mem:// for in memory cache

#
#$ NGINX
#
NGINX_PORT=8080 # pooled cache-proxy listen port (only port to publish)
```

## Nginx cache proxy

Single pooled URL: `http://localhost:8080` (`NGINX_PORT` in `.env`).
Upstream is the `api` service on `STOCKSAPI_PORT` (3200); ports are never
hardcoded in `nginx/` — `default.conf.template` renders via envsubst.

- `/stocks/*` GETs are cached (`X-Cache-Status: HIT/MISS`, key splits on
  `X-MCP` so compact vs full wire formats stay separate). TTLs mirror the
  backend: 6h bulk, 15s live quotes.
- `/wallet/ /auth/ /user/ /orunmila/ /mcp` proxy with caching OFF (BYPASS).

BFF repoint (the ONE var): set `GATEWAY_API=http://localhost:8080`
(`frontend/.env.example`) so the Next.js proxy BFF talks to nginx instead
of `http://localhost:3200` directly. Nothing under `frontend/` is changed
by this repo.

## Health Check

```bash
curl http://localhost:3200/health
```

## License

Mansa Team's MODIFIED GPL 3.0 License. See LICENSE for details.
