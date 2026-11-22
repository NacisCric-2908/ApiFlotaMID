"""Adaptador de ZonasPort: consulta a Viajes y zonas a través del gateway, con el token de este MID.

Usa `GET /zonas/verificar?lat&lng`, que responde `{"permitida": false, "zonas": [...]}`; `permitida: false`
significa que el punto cae en una zona prohibida.
"""

import httpx

from app.adaptadores.salida.http import enviar, json_o_error
from app.adaptadores.salida.token import TokenGateway
from app.dominio.errores import ServicioNoDisponible

SERVICIO = "viajes-zonas"


class ZonasHttp:
    def __init__(
        self, http: httpx.AsyncClient, gateway_url: str, ruta: str, tokens: TokenGateway, *, reintentos: int, backoff_s: float
    ):
        self._http = http
        self._url = gateway_url.rstrip("/") + ruta
        self._tokens = tokens
        self._reintentos, self._backoff_s = reintentos, backoff_s

    async def esta_en_zona_prohibida(self, lat: float, lng: float) -> bool:
        for primer_intento in (True, False):
            token = await self._tokens.obtener()
            r = await enviar(
                self._http, SERVICIO, "GET", self._url,
                params={"lat": lat, "lng": lng}, headers={"Authorization": f"Bearer {token}"},
                reintentos=self._reintentos, backoff_s=self._backoff_s,
            )
            if r.status_code == 401 and primer_intento:
                self._tokens.invalidar()  # el token pudo vencer o revocarse: se pide uno nuevo y se reintenta una vez
                continue
            break
        datos = json_o_error(SERVICIO, r)
        permitida = datos.get("permitida") if isinstance(datos, dict) else None
        if not isinstance(permitida, bool):
            raise ServicioNoDisponible(SERVICIO, "respuesta_inesperada")
        return not permitida
