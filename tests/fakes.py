"""Dobles de prueba de los puertos y fábrica de vehículos."""

import asyncio
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from app.dominio.modelos import Vehiculo

AHORA = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)


def vehiculo(
    id: str = "v1",
    bateria: int = 80,
    estado: str = "disponible",
    distancia: float | None = 100.0,
    lat: float = 4.7110,
    lng: float = -74.0721,
    tipo: str = "scooter",
    minutos_sin_actualizar: int = 0,
) -> Vehiculo:
    return Vehiculo(
        id=id,
        tipo=tipo,
        bateria_pct=bateria,
        estado=estado,
        lat=lat,
        lng=lng,
        actualizado_en=AHORA - timedelta(minutes=minutos_sin_actualizar),
        distancia_m=distancia,
    )


class VehiculosFalso:
    def __init__(self, cercanos: Iterable[Vehiculo] = (), todos: Iterable[Vehiculo] = (), error: Exception | None = None):
        self.cercanos, self.todos, self.error = list(cercanos), list(todos), error
        self.llamadas: list[dict] = []

    async def buscar_cercanos(self, lat, lng, radio_m, tipo, bateria_min):
        self.llamadas.append({"lat": lat, "lng": lng, "radio_m": radio_m, "tipo": tipo, "bateria_min": bateria_min})
        if self.error:
            raise self.error
        return list(self.cercanos)

    async def listar_todos(self):
        self.llamadas.append({"todos": True})
        if self.error:
            raise self.error
        return list(self.todos)


class ZonasFalso:
    """Marca como zona prohibida las coordenadas de los vehículos indicados."""

    def __init__(self, prohibidos: Iterable[Vehiculo] = (), error: Exception | None = None):
        self.prohibidas = {(v.lat, v.lng) for v in prohibidos}
        self.error = error
        self.consultas: list[tuple[float, float]] = []
        self.simultaneas = 0
        self.maximo_simultaneas = 0

    async def esta_en_zona_prohibida(self, lat, lng):
        self.consultas.append((lat, lng))
        self.simultaneas += 1
        self.maximo_simultaneas = max(self.maximo_simultaneas, self.simultaneas)
        try:
            await asyncio.sleep(0)  # cede el control para que se vea la concurrencia
            if self.error:
                raise self.error
            return (lat, lng) in self.prohibidas
        finally:
            self.simultaneas -= 1


class RelojFalso:
    def __init__(self, ahora: datetime = AHORA):
        self._ahora = ahora

    def ahora(self) -> datetime:
        return self._ahora
