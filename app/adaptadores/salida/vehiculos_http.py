"""Adaptador de VehiculosPort: lee los vehículos del CRUD de Flota (llamada entre servicios, sin gateway).

El CRUD exige la cabecera `X-Gateway-Secret` con su propio secreto. Las listas vienen paginadas (hasta 100 por
página): se leen todas las páginas hasta `max_paginas`.
"""

import logging
from datetime import datetime

import httpx

from app.adaptadores.salida.http import enviar, json_o_error
from app.dominio.errores import ServicioNoDisponible
from app.dominio.modelos import Vehiculo

SERVICIO = "flota-crud"
TAMANO_PAGINA = 100  # el máximo que acepta el CRUD
log = logging.getLogger(__name__)


def a_vehiculo(item: dict) -> Vehiculo:
    lng, lat = item["ubicacion"]["coordinates"]  # GeoJSON: [longitud, latitud]
    return Vehiculo(
        id=item["id"],
        tipo=item["tipo"],
        bateria_pct=int(item["bateriaPct"]),
        estado=item["estado"],
        lat=float(lat),
        lng=float(lng),
        actualizado_en=datetime.fromisoformat(item["actualizadoEn"]),
        distancia_m=float(item["distanciaMetros"]) if item.get("distanciaMetros") is not None else None,
        localidad=(item.get("localidad") or {}).get("nombre"),
    )


class VehiculosHttp:
    def __init__(
        self, http: httpx.AsyncClient, base_url: str, secreto: str, *, reintentos: int, backoff_s: float,
        max_paginas: int = 10, tamano_pagina: int = TAMANO_PAGINA,
    ):
        self._http = http
        self._url = base_url.rstrip("/") + "/vehiculos"
        self._cabeceras = {"X-Gateway-Secret": secreto}
        self._reintentos, self._backoff_s = reintentos, backoff_s
        self._max_paginas, self._tamano = max_paginas, tamano_pagina

    async def buscar_cercanos(
        self, lat: float, lng: float, radio_m: float, tipo: str | None, bateria_min: int | None
    ) -> list[Vehiculo]:
        params: dict = {"lat": lat, "lng": lng, "radioMetros": radio_m, "estado": "disponible"}
        if tipo:
            params["tipo"] = tipo
        if bateria_min is not None:
            params["bateriaMin"] = bateria_min
        return await self._leer_paginas(params)

    async def listar_todos(self) -> list[Vehiculo]:
        return await self._leer_paginas({})

    async def _leer_paginas(self, filtros: dict) -> list[Vehiculo]:
        vehiculos: list[Vehiculo] = []
        for pagina in range(1, self._max_paginas + 1):
            r = await enviar(
                self._http, SERVICIO, "GET", self._url,
                params={**filtros, "pagina": pagina, "tamano": self._tamano}, headers=self._cabeceras,
                reintentos=self._reintentos, backoff_s=self._backoff_s,
            )
            datos = json_o_error(SERVICIO, r)
            try:
                vehiculos += [a_vehiculo(item) for item in datos["items"]]
                total = int(datos["total"])
                hay_mas = bool(datos["items"])
            except (KeyError, ValueError, TypeError, AttributeError):
                raise ServicioNoDisponible(SERVICIO, "respuesta_inesperada") from None
            if len(vehiculos) >= total or not hay_mas:
                return vehiculos
        log.warning("El CRUD de Flota tiene más de %s vehículos para esta consulta: se leyeron solo %s páginas",
                    self._max_paginas * self._tamano, self._max_paginas)
        return vehiculos
