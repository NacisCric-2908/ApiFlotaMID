# Atajos. Todo corre dentro de Docker.
.PHONY: up down logs test openapi lock add

up:       ## Levanta el MID con el simulador de los servicios de los que depende (http://localhost:8100)
	docker compose --profile simulado up -d --build

down:     ## Detiene todo
	docker compose --profile simulado down

logs:
	docker compose logs -f mid

test:     ## Pruebas (sin red: los servicios externos se simulan)
	docker compose --profile test run --rm --build test

openapi:  ## Regenera docs/openapi.json
	docker compose run --rm --no-deps -T mid python -c "import json; from app.main import app; print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))" > docs/openapi.json

UV = docker run --rm --user $(shell id -u):$(shell id -g) -e HOME=/tmp -e UV_CACHE_DIR=/tmp/uv-cache \
     -v $(CURDIR):/work -w /work ghcr.io/astral-sh/uv:python3.12-bookworm-slim uv

lock:     ## Re-resuelve y actualiza uv.lock
	$(UV) lock

add:      ## Agrega una dependencia: make add pkg=httpx  (dev: make add pkg="--dev pytest-cov")
	$(UV) add $(pkg)
