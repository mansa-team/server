help h:
	@echo "Available commands:"
	@echo "  make run      - Restart containers"
	@echo "  make down     - Stop containers"
	@echo "  make logs-api - View API logs"

run r:
	docker compose down --remove-orphans
	docker compose up -d --build

down d:
	docker compose down --remove-orphans

logs-% l-%:
	docker logs -f server-$*-1