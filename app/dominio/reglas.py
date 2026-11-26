"""Reglas de negocio del MID de Flota, como funciones puras y fáciles de probar.

Los valores por defecto son los del documento de requisitos del clúster; la aplicación los toma de variables de
entorno (ver app/config.py).
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.dominio.modelos import Prioridad

RADIO_TIERRA_M = 6_378_137  # el que usa MongoDB en las consultas esféricas


@dataclass(frozen=True)
class ReglasRecomendacion:
    radio_m: float = 500  # RADIO_BUSQUEDA_M
    bateria_minima: int = 25  # BATERIA_MINIMA: por debajo, no se recomienda
    max_resultados: int = 3
    concurrencia_zonas: int = 10


@dataclass(frozen=True)
class ReglasAlertas:
    bateria_alerta: int = 15  # por debajo: alerta
    bateria_alerta_alta: int = 10  # por debajo: prioridad alta
    horas_sin_actualizar: float = 2  # más de esto sin actualizar la ubicación: alerta
    # Estados que se evalúan. Un vehículo en viaje no se puede recoger y su ubicación no se actualiza
    # durante el trayecto; uno en mantenimiento ya está en manos del equipo operativo.
    estados: frozenset[str] = frozenset({"disponible"})
    concurrencia_zonas: int = 10


def distancia_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia sobre la esfera (haversine), en metros. Solo se usa si el CRUD no trae la distancia."""
    f1, f2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((f2 - f1) / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(a))


def puntaje(distancia_metros: float, bateria_pct: int) -> float:
    """Menor es mejor: premia al vehículo cercano y con más batería (cada 1 % de batería vale 2 m)."""
    return distancia_metros - bateria_pct * 2


def prioridad_por_bateria(bateria_pct: int, reglas: ReglasAlertas) -> Prioridad:
    return Prioridad.ALTA if bateria_pct < reglas.bateria_alerta_alta else Prioridad.MEDIA


def minutos_sin_actualizar(ahora: datetime, actualizado_en: datetime) -> int:
    return max(0, int((ahora - actualizado_en).total_seconds() // 60))


def esta_desactualizado(ahora: datetime, actualizado_en: datetime, reglas: ReglasAlertas) -> bool:
    """Estrictamente más de `horas_sin_actualizar`: justo en el límite todavía no es alerta."""
    return (ahora - actualizado_en) > timedelta(hours=reglas.horas_sin_actualizar)
