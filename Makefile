# Faultzy developer commands. Requires uv (Python) and npm (Node 18+).
.PHONY: setup api web dev test typecheck build check check-bedrock fixtures demo-smoke text-me clean

setup:            ## Install backend and frontend dependencies
	cd backend && uv sync --extra dev
	cd frontend && npm install

api:              ## Run the FastAPI backend on :8000 (auto-reload)
	cd backend && uv run uvicorn faultzy.main:app --reload --port 8000

web:              ## Run the Vite frontend on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

dev:              ## Run backend and frontend together (Ctrl+C stops both)
	$(MAKE) -j2 api web

test:             ## Backend tests
	cd backend && uv run pytest

typecheck:        ## Frontend type check
	cd frontend && npx tsc -b --noEmit

build:            ## Frontend production build
	cd frontend && npm run build

check: test typecheck build   ## Everything CI would run

demo-smoke:       ## Exercise the normal -> anomalous scenario against a running API
	cd backend && uv run python scripts/demo_smoke.py

text-me:          ## Trigger a fault and send (or show) the technician text and link
	cd backend && uv run python scripts/text_me.py

check-bedrock:    ## Verify Bedrock model access with your AWS credentials
	cd backend && uv run python scripts/check_bedrock.py

fixtures:         ## Regenerate simulated telemetry fixtures
	cd backend && uv run python scripts/generate_fixtures.py

clean:
	rm -rf backend/.venv backend/.pytest_cache frontend/node_modules frontend/dist
