"""Llamadas HTTP a otros servicios con reintentos limitados y un único tipo de error."""

import asyncio
from typing import Any

import httpx

from app.dominio.errores import ServicioNoDisponible


async def enviar(
    http: httpx.AsyncClient,
    servicio: str,
    metodo: str,
    url: str,
    *,
    reintentos: int,
    backoff_s: float,
    **kwargs: Any,
) -> httpx.Response:
    """Envía la petición y reintenta solo lo transitorio: cortes de red, timeouts, 429 y 5xx.

    La espera entre intentos se duplica (backoff exponencial). Cualquier otra respuesta, incluidos los 4xx, se
    devuelve tal cual para que quien llama decida (por ejemplo, renovar el token ante un 401). Si se agotan los
    intentos lanza `ServicioNoDisponible`.
    """
    motivo = "desconocido"
    for intento in range(reintentos + 1):
        try:
            r = await http.request(metodo, url, **kwargs)
        except httpx.TransportError as e:  # incluye timeouts y fallos de conexión
            motivo = type(e).__name__
        else:
            if r.status_code != 429 and r.status_code < 500:
                return r
            motivo = f"http_{r.status_code}"
        if intento < reintentos:
            await asyncio.sleep(backoff_s * 2**intento)
    raise ServicioNoDisponible(servicio, motivo)


def json_o_error(servicio: str, r: httpx.Response) -> Any:
    """El cuerpo JSON de una respuesta 200; cualquier otra cosa es un servicio que no respondió bien."""
    if r.status_code != 200:
        raise ServicioNoDisponible(servicio, f"http_{r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise ServicioNoDisponible(servicio, "respuesta_no_json") from None
