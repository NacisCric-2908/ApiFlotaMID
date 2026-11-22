"""Arma los casos de uso con los adaptadores que haya en la aplicación (reales o, en pruebas, simulados)."""

from dataclasses import dataclass

from fastapi import Request

from app.dominio.alertas import GenerarAlertas
from app.dominio.puertos import RelojPort, VehiculosPort, ZonasPort
from app.dominio.recomendar import RecomendarVehiculo
from app.dominio.reglas import ReglasAlertas, ReglasRecomendacion


@dataclass
class Contenedor:
    vehiculos: VehiculosPort
    zonas: ZonasPort
    reloj: RelojPort
    reglas_recomendacion: ReglasRecomendacion
    reglas_alertas: ReglasAlertas


def caso_recomendar(request: Request) -> RecomendarVehiculo:
    c: Contenedor = request.app.state.contenedor
    return RecomendarVehiculo(c.vehiculos, c.zonas, c.reglas_recomendacion)


def caso_alertas(request: Request) -> GenerarAlertas:
    c: Contenedor = request.app.state.contenedor
    return GenerarAlertas(c.vehiculos, c.zonas, c.reloj, c.reglas_alertas)
