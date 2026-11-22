from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def instalar_contrato(app: FastAPI) -> None:
    """Genera el OpenAPI sin el 422 por defecto de FastAPI: este servicio responde 400 (ver errores.py)."""

    def openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        esquema = get_openapi(
            title=app.title, version=app.version, description=app.description, routes=app.routes,
            tags=app.openapi_tags, servers=app.servers,
        )  # fmt: skip
        for operaciones in esquema["paths"].values():
            for operacion in operaciones.values():
                operacion["responses"].pop("422", None)
        for nombre in ("HTTPValidationError", "ValidationError"):
            esquema["components"]["schemas"].pop(nombre, None)
        app.openapi_schema = esquema
        return esquema

    app.openapi = openapi
