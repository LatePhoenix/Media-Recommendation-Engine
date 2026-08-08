.PHONY: up down migrate seed test lint logs ready

COMPOSE = docker compose -f infra/docker-compose.yml
COMPOSE_DEV = docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

dev:
	$(COMPOSE_DEV) up --build

migrate:
	$(COMPOSE) exec api alembic upgrade head

seed:
	$(COMPOSE) exec api python -m app.seed

test:
	cd apps/api && python -m pytest app/tests workers/importers/tests -q --tb=short 2>/dev/null || \
		(cd apps/api && PYTHONPATH=../..:../../packages:. python -m unittest discover -s app/tests -v)

lint:
	cd apps/api && python -m compileall app
	cd apps/web && npm run build

logs:
	$(COMPOSE) logs -f --tail=200

ready:
	curl -sf http://127.0.0.1:8000/health/ready | python -m json.tool
