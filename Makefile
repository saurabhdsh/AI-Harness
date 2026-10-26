.PHONY: setup dev test lint migrate seed-demo smoke-test down logs build

setup:
	@echo "==> Installing control-plane deps"
	cd services/control-plane && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	@echo "==> Installing mission-control deps"
	cd apps/mission-control && npm install
	@echo "==> Installing langgraph reference agent deps"
	cd examples/langgraph-agent && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cp -n .env.example .env || true
	@echo "Setup complete. Run: make dev"

dev:
	docker compose up --build -d postgres redis langgraph-agent rest-agent control-plane seed
	@echo "Waiting for control-plane..."
	@sleep 8
	cd apps/mission-control && npm run dev

build:
	docker compose build

down:
	docker compose down

logs:
	docker compose logs -f control-plane langgraph-agent

migrate:
	cd services/control-plane && . .venv/bin/activate && alembic upgrade head

seed-demo:
	docker compose run --rm seed

test:
	cd services/control-plane && . .venv/bin/activate && pytest -q
	cd apps/mission-control && npm run build

lint:
	cd apps/mission-control && npx tsc --noEmit

smoke-test:
	./scripts/smoke-test.sh
