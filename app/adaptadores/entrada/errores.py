"""Formato de error común del clúster: {"codigo": ..., "mensaje": ..., "detalle": {}}."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.dominio.errores import ServicioNoDisponible

log = logging.getLogger(__name__)

MENSAJES_503 = {
    "flota-crud": "No se pudo consultar el servicio de vehículos de Flota.",
    "viajes-zonas": "No se pudo consultar Viajes y zonas: sin validar las zonas no se recomienda ningún vehículo.",
    "gateway-token": "No se pudo obtener el token del gateway para consultar a otros servicios.",
}


def cuerpo_error(codigo: str, mensaje: str, detalle: Any = None) -> dict:
    return {"codigo": codigo, "mensaje": mensaje, "detalle": detalle if detalle is not None else {}}


def _respuesta(status_code: int, codigo: str, mensaje: str, detalle: Any = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=cuerpo_error(codigo, mensaje, detalle))


async def _servicio_no_disponible(_: Request, exc: ServicioNoDisponible) -> JSONResponse:
    log.warning("Servicio no disponible: %s (%s)", exc.servicio, exc.motivo)
    mensaje = MENSAJES_503.get(exc.servicio, "No se pudo consultar un servicio del que depende este.")
    return _respuesta(503, "servicio_no_disponible", mensaje, {"servicio": exc.servicio, "motivo": exc.motivo})


async def _validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
    # El enunciado pide 400 (no el 422 por defecto de FastAPI) para datos inválidos.
    errores = [
        {"campo": ".".join(str(p) for p in (e["loc"][1:] or e["loc"])), "mensaje": e["msg"]} for e in exc.errors()
    ]
    return _respuesta(400, "solicitud_invalida", "Los datos enviados no son válidos.", {"errores": errores})


async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    codigos = {404: "no_encontrado", 405: "metodo_no_permitido"}
    return _respuesta(exc.status_code, codigos.get(exc.status_code, "error_http"), str(exc.detail))


async def _inesperado(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Error inesperado", exc_info=exc)
    return _respuesta(500, "error_interno", "Ocurrió un error inesperado.")


def registrar_manejadores(app: FastAPI) -> None:
    app.add_exception_handler(ServicioNoDisponible, _servicio_no_disponible)
    app.add_exception_handler(RequestValidationError, _validacion)
    app.add_exception_handler(StarletteHTTPException, _http)
    app.add_exception_handler(Exception, _inesperado)
