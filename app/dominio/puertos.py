"""Puertos de salida: lo que el núcleo necesita del mundo exterior, expresado como interfaces.

El núcleo solo conoce estas interfaces. Qué hay detrás (HTTP al CRUD de Flota, HTTP a Viajes y zonas a través
del gateway, un reloj, o un simulado en las pruebas) lo deciden los adaptadores.
"""

from datetime import datetime
from typing import Protocol

from app.dominio.modelos import Vehiculo


class VehiculosPort(Protocol):
    async def buscar_cercanos(
        self, lat: float, lng: float, radio_m: float, tipo: str | None, bateria_min: int | None
    ) -> list[Vehiculo]:
        """Vehículos `disponible` dentro del radio, del más cercano al más lejano, con `distancia_m`.

        Lanza `ServicioNoDisponible` si el servicio de vehículos no responde.
        """
        ...

    async def listar_todos(self) -> list[Vehiculo]:
        """Todos los vehículos (de cualquier estado). Lanza `ServicioNoDisponible` si no responde."""
        ...


class ZonasPort(Protocol):
    async def esta_en_zona_prohibida(self, lat: float, lng: float) -> bool:
        """Lanza `ServicioNoDisponible` si Viajes y zonas no responde."""
        ...


class RelojPort(Protocol):
    def ahora(self) -> datetime:
        """La hora actual, con zona horaria (UTC)."""
        ...
