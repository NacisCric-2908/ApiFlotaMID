"""Esquemas de las respuestas HTTP (el contrato). Traducen desde los modelos del dominio."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.dominio.modelos import Alerta, Candidato, Recomendacion, ResultadoAlertas, Vehiculo

Tipo = Literal["scooter", "bicicleta"]


class Punto(BaseModel):
    """Punto GeoJSON. Ojo: el orden de las coordenadas es [longitud, latitud]."""

    type: Literal["Point"] = "Point"
    coordinates: Annotated[list[float], Field(min_length=2, max_length=2)]


def _punto(v: Vehiculo) -> Punto:
    return Punto(coordinates=[v.lng, v.lat])


class VehiculoRecomendado(BaseModel):
    vehiculoId: str
    tipo: Tipo
    distanciaMetros: float = Field(description="Distancia desde el punto pedido, sobre la esfera, en metros.")
    bateriaPct: int
    puntaje: float = Field(description="`distanciaMetros - bateriaPct * 2`. Menor es mejor.")
    ubicacion: Punto
    localidad: str | None = Field(default=None, description="Localidad de Bogotá donde está el vehículo.")


class Recomendaciones(BaseModel):
    recomendaciones: list[VehiculoRecomendado] = Field(description="Hasta 3, del mejor al peor puntaje.")
    total: int
    motivo: Literal["sin_vehiculos_cercanos", "todos_en_zona_prohibida"] | None = Field(
        default=None, description="Solo aparece si la lista está vacía: por qué no hay recomendaciones."
    )


def a_recomendaciones(r: Recomendacion) -> Recomendaciones:
    def item(c: Candidato) -> VehiculoRecomendado:
        v = c.vehiculo
        return VehiculoRecomendado(
            vehiculoId=v.id, tipo=v.tipo, distanciaMetros=round(c.distancia_m, 1), bateriaPct=v.bateria_pct,
            puntaje=round(c.puntaje, 1), ubicacion=_punto(v), localidad=v.localidad,
        )  # fmt: skip

    return Recomendaciones(
        recomendaciones=[item(c) for c in r.candidatos], total=len(r.candidatos), motivo=r.motivo.value if r.motivo else None
    )


class AlertaSalida(BaseModel):
    vehiculoId: str
    tipoAlerta: Literal["bateria_baja", "zona_prohibida", "sin_actualizar"]
    prioridad: Literal["alta", "media"] = Field(
        description="`alta` si la batería es menor a 10 % o está en zona prohibida; `media` en los demás casos."
    )
    detalle: str
    tipo: Tipo
    estado: str
    bateriaPct: int
    ubicacion: Punto
    localidad: str | None = None
    actualizadoEn: datetime
    minutosSinActualizar: int


class Alertas(BaseModel):
    alertas: list[AlertaSalida] = Field(
        description="Una alerta por cada condición que cumple un vehículo, ordenadas por prioridad y luego por "
        "tiempo sin actualizar (la más antigua primero)."
    )
    total: int
    advertencias: list[Literal["zonas_no_verificadas"]] = Field(
        default_factory=list,
        description="`zonas_no_verificadas`: Viajes y zonas no respondió; faltan las alertas de zona prohibida.",
    )


def a_alertas(r: ResultadoAlertas) -> Alertas:
    def item(a: Alerta) -> AlertaSalida:
        v = a.vehiculo
        return AlertaSalida(
            vehiculoId=v.id, tipoAlerta=a.tipo.value, prioridad=a.prioridad.value, detalle=a.detalle, tipo=v.tipo,
            estado=v.estado, bateriaPct=v.bateria_pct, ubicacion=_punto(v), localidad=v.localidad,
            actualizadoEn=v.actualizado_en, minutosSinActualizar=a.minutos_sin_actualizar,
        )  # fmt: skip

    return Alertas(alertas=[item(a) for a in r.alertas], total=len(r.alertas), advertencias=list(r.advertencias))


class ErrorRespuesta(BaseModel):
    """Formato de error común a todos los servicios del clúster."""

    codigo: str
    mensaje: str
    detalle: Any = {}
