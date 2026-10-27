.PHONY: setup setup-local dev dev-local stop-local domain-agents register-domain-agents test lint migrate seed-demo smoke-test down logs build

setup:
	@echo "==> Installing control-plane deps"
	cd services/control-plane && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	@echo "==> Installing mission-control deps"
	cd apps/mission-control && npm install
	@echo "==> Installing OpenAI/Azure LangGraph agent deps"
	cd examples/langgraph-openai-agent && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	@echo "==> Installing domain-agents (AD/AMS/QE) deps"
	cd examples/domain-agents && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cp -n .env.example .env || true
	@echo "Setup complete. With Docker: make dev  |  Without Docker: make dev-local"

setup-local: setup
	@echo "Local (no Docker) ready. Configure .env then: make dev-local"

dev:
	docker compose up --build -d postgres redis langgraph-agent rest-agent control-plane seed
	@echo "Waiting for control-plane..."
	@sleep 8
	cd apps/mission-control && npm run dev

# No Docker — SQLite + local Python/Node processes
dev-local:
	chmod +x scripts/dev-local.sh scripts/stop-local.sh
	./scripts/dev-local.sh

stop-local:
	chmod +x scripts/stop-local.sh
	./scripts/stop-local.sh

# AD / AMS / QE domain LLM agents only (port 8091)
domain-agents:
	@if [ ! -d examples/domain-agents/.venv ]; then \
	  cd examples/domain-agents && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt; \
	fi
	cd examples/domain-agents && . .venv/bin/activate && uvicorn main:app --host 127.0.0.1 --port 8091

register-domain-agents:
	chmod +x scripts/register-domain-agents.sh
	./scripts/register-domain-agents.sh

# Post-deploy CI registration (set EXTERNAL_ID + INVOKE_URL)
ci-register-agent:
	chmod +x scripts/ci-register-agent.sh
	./scripts/ci-register-agent.sh

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

# Verify Azure/OpenAI keys from .env (same pattern as test_llm.py)
test-llm:
	@if [ -x examples/langgraph-openai-agent/.venv/bin/python ]; then \
	  examples/langgraph-openai-agent/.venv/bin/python scripts/test_llm.py; \
	elif [ -x services/control-plane/.venv/bin/python ]; then \
	  services/control-plane/.venv/bin/pip install -q openai >/dev/null; \
	  services/control-plane/.venv/bin/python scripts/test_llm.py; \
	else \
	  python3 -m pip install -q openai && python3 scripts/test_llm.py; \
	fi
