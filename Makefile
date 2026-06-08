help h:
	@echo "Available commands:"
	@echo "  make run      - Restart containers"
	@echo "  make down     - Stop containers"
	@echo "  make logs-api - View API logs"
	@echo "  make ci       - Run CI checks (auto-fix + lint + mypy + tests + security)"
	@echo "  make c        - Same as ci"
	@echo "  make lint     - Lint only (auto-fix + check)"
	@echo "  make test     - Tests only"
	@echo "  make type     - mypy only"
	@echo "  make fmt      - Auto-format only"
	@echo "  make fast     - Quick CI (skip mypy + bandit)"

ci c:
	./ci.ps1

lint:
	./ci.ps1 -Lint

test:
	./ci.ps1 -Test

type:
	./ci.ps1 -Typecheck

fmt:
	ruff format .

fast:
	./ci.ps1 -Fast

run r:
	docker compose down --remove-orphans
	docker compose up -d --build

down d:
	docker compose down --remove-orphans

logs-% l-%:
	docker logs -f server-$*-1