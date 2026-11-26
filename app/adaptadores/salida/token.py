"""Token del gateway para llamar a otros grupos (OAuth2 «client credentials»).

El gateway emite un token por MID con sus alcances. Este adaptador lo pide, lo guarda hasta poco antes de que
venza y lo renueva solo; varias peticiones simultáneas comparten una única solicitud.

Supone el flujo estándar: POST de formulario con `grant_type=client_credentials` a la ruta `/token` del gateway y
respuesta JSON con `access_token` y `expires_in` (segundos). Si el gateway publica otra forma, solo cambia este
archivo.
"""

import asyncio
import time
from collections.abc import Callable

import httpx

from app.adaptadores.salida.http import enviar
from app.dominio.errores import ServicioNoDisponible

SERVICIO = "gateway-token"
VIGENCIA_POR_DEFECTO_S = 300


class TokenGateway:
    def __init__(
        self,
        http: httpx.AsyncClient,
        url: str,
        client_id: str,
        client_secret: str,
        scope: str,
        *,
        reintentos: int,
        backoff_s: float,
        reloj: Callable[[], float] = time.monotonic,
        margen_s: float = 30.0,
    ):
        self._http, self._url = http, url
        self._form = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        }
        self._reintentos, self._backoff_s = reintentos, backoff_s
        self._reloj, self._margen_s = reloj, margen_s
        self._token: str | None = None
        self._vence = 0.0
        self._candado = asyncio.Lock()

    def _vigente(self) -> bool:
        return self._token is not None and self._reloj() < self._vence

    async def obtener(self) -> str:
        if self._vigente():
            return self._token  # type: ignore[return-value]
        async with self._candado:
            if self._vigente():  # otra petición ya lo renovó mientras esperábamos
                return self._token  # type: ignore[return-value]
            r = await enviar(
                self._http, SERVICIO, "POST", self._url, data=self._form,
                reintentos=self._reintentos, backoff_s=self._backoff_s,
            )
            if r.status_code != 200:
                raise ServicioNoDisponible(SERVICIO, f"http_{r.status_code}")
            try:
                datos = r.json()
                token = datos["access_token"]
                vigencia = float(datos.get("expires_in", VIGENCIA_POR_DEFECTO_S))
            except (ValueError, KeyError, TypeError, AttributeError):
                raise ServicioNoDisponible(SERVICIO, "respuesta_inesperada") from None
            if not isinstance(token, str) or not token:
                raise ServicioNoDisponible(SERVICIO, "respuesta_inesperada")
            self._token, self._vence = token, self._reloj() + max(0.0, vigencia - self._margen_s)
            return token

    def invalidar(self) -> None:
        """Olvida el token (p. ej. porque Viajes y zonas respondió 401): el próximo `obtener` pide uno nuevo."""
        self._token = None
