"""Núcleo del MID: modelos del dominio.

No dependen de FastAPI, de httpx ni de ningún servicio externo: son datos puros que usan las reglas y los
casos de uso. Los adaptadores se encargan de traducir hacia y desde ellos.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MotivoVacio(StrEnum):
    """Por qué una recomendación no trae vehículos."""

    SIN_VEHICULOS_CERCANOS = "sin_vehiculos_cercanos"
    TODOS_EN_ZONA_PROHIBIDA = "todos_en_zona_prohibida"


class TipoAlerta(StrEnum):
    BATERIA_BAJA = "bateria_baja"
    ZONA_PROHIBIDA = "zona_prohibida"
    SIN_ACTUALIZAR = "sin_actualizar"


class Prioridad(StrEnum):
    ALTA = "alta"
    MEDIA = "media"


@dataclass(frozen=True, slots=True)
class Vehiculo:
    id: str
    tipo: str  # "scooter" o "bicicleta"
    bateria_pct: int
    estado: str  # "disponible", "en_viaje" o "mantenimiento"
    lat: float
    lng: float
    actualizado_en: datetime
    distancia_m: float | None = None  # solo viene en las búsquedas por cercanía
    localidad: str | None = None


@dataclass(frozen=True, slots=True)
class Candidato:
    vehiculo: Vehiculo
    distancia_m: float
    puntaje: float  # menor es mejor


@dataclass(frozen=True, slots=True)
class Recomendacion:
    candidatos: tuple[Candidato, ...]
    motivo: MotivoVacio | None = None  # solo si no hay candidatos


@dataclass(frozen=True, slots=True)
class Alerta:
    vehiculo: Vehiculo
    tipo: TipoAlerta
    prioridad: Prioridad
    detalle: str
    minutos_sin_actualizar: int


@dataclass(frozen=True, slots=True)
class ResultadoAlertas:
    alertas: tuple[Alerta, ...]
    # Avisos de que el resultado es parcial, p. ej. «zonas_no_verificadas» si Viajes y zonas no respondió.
    advertencias: tuple[str, ...] = ()
