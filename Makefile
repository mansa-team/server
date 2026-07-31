PS = pwsh -NoProfile -ExecutionPolicy Bypass

help h:
	@echo "Available commands:"
	@echo "  make run      - Restart containers"
	@echo "  make down     - Stop containers"
	@echo "  make logs-api - View API logs"
	@echo "  make ci       - Run CI checks (auto-fix + lint + mypy + tests + security)"
	
ci c:
	$(PS) -File ci.ps1

run r:
	docker compose down --remove-orphans
	docker compose up -d --build
	docker logs -f server-api-1

down d:
	docker compose down --remove-orphans

logs-% l-%:
	docker logs -f server-$*-1
