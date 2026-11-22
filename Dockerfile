FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.9.30 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /srv
RUN useradd --create-home --uid 10001 app
# Primero solo los archivos de dependencias: la capa se reutiliza mientras no cambien.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app

# Simulador de los servicios de los que depende el MID (CRUD de Flota, Viajes y zonas, token del gateway).
# Solo para desarrollo y pruebas: docker compose --profile simulado up
FROM base AS simulador
COPY simuladores ./simuladores
USER app
EXPOSE 9000
CMD ["uvicorn", "simuladores.upstream:app", "--host", "0.0.0.0", "--port", "9000"]

# Imagen de pruebas: docker compose --profile test run --rm test
FROM base AS test
RUN uv sync --frozen --no-install-project
COPY pytest.ini ./
COPY simuladores ./simuladores
COPY docs ./docs
COPY tests ./tests
USER app
CMD ["pytest", "-q"]

# Imagen final (es la última etapa, por lo tanto la predeterminada)
FROM base AS prod
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
