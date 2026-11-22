from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security

from app.adaptadores.entrada.alcances import ALERTAS_LEER, RECOMENDACIONES_LEER, cabecera_gateway, oauth2
from app.adaptadores.entrada.dependencias import caso_alertas, caso_recomendar
from app.adaptadores.entrada.esquemas import (
    Alertas,
    ErrorRespuesta,
    Recomendaciones,
    Tipo,
    a_alertas,
    a_recomendaciones,
)
from app.dominio.alertas import GenerarAlertas
from app.dominio.recomendar import RecomendarVehiculo

router = APIRouter(
    dependencies=[Security(cabecera_gateway)],
    responses={
        401: {"model": ErrorRespuesta, "description": "Falta la cabecera secreta del gateway"},
        500: {"model": ErrorRespuesta, "description": "Error interno"},
    },
)


@router.get(
    "/recomendaciones/vehiculo",
    tags=["Recomendaciones"],
    operation_id="recomendarVehiculo",
    response_model=Recomendaciones,
    response_model_exclude_none=True,
    summary="Los 3 mejores vehículos cerca de un punto",
    description=(
        "Reglas, en orden: (1) vehículos `disponible` a 500 m o menos; (2) se descartan los de batería menor a 25 %; "
        "(3) se descartan los que están en una zona prohibida (se consulta a Viajes y zonas); (4) se ordena por "
        "`puntaje = distanciaMetros - bateriaPct * 2` (menor es mejor) y se devuelven los 3 mejores. Si no queda "
        "ninguno, responde **200** con la lista vacía y un `motivo`. Si Viajes y zonas no responde, responde **503**: "
        "no se recomienda un vehículo sin validar las zonas."
    ),
    dependencies=[Security(oauth2, scopes=[RECOMENDACIONES_LEER])],
    responses={
        400: {"model": ErrorRespuesta, "description": "Parámetros inválidos"},
        503: {"model": ErrorRespuesta, "description": "Viajes y zonas o el servicio de vehículos no responden"},
    },
)
async def recomendar_vehiculo(
    caso: Annotated[RecomendarVehiculo, Depends(caso_recomendar)],
    lat: Annotated[float, Query(ge=-90, le=90, description="Latitud del punto donde está el usuario.")],
    lng: Annotated[float, Query(ge=-180, le=180, description="Longitud del punto donde está el usuario.")],
    tipo: Annotated[Tipo | None, Query(description="Si se indica, solo vehículos de ese tipo.")] = None,
):
    return a_recomendaciones(await caso.ejecutar(lat, lng, tipo))


@router.get(
    "/flota/alertas",
    tags=["Alertas"],
    operation_id="listarAlertas",
    response_model=Alertas,
    summary="Vehículos que requieren atención del equipo operativo",
    description=(
        "Un vehículo `disponible` genera una alerta por cada condición que cumple: batería menor a 15 % "
        "(`bateria_baja`; prioridad **alta** si es menor a 10 %, **media** si no), está en una zona prohibida "
        "(`zona_prohibida`; **alta**), o su ubicación no se actualiza hace más de 2 horas (`sin_actualizar`; "
        "**media**). Ordenadas por prioridad y luego por tiempo sin actualizar (la más antigua primero). Si Viajes y "
        "zonas no responde, **no falla**: devuelve las demás alertas y la advertencia `zonas_no_verificadas`."
    ),
    dependencies=[Security(oauth2, scopes=[ALERTAS_LEER])],
    responses={503: {"model": ErrorRespuesta, "description": "El servicio de vehículos no responde"}},
)
async def listar_alertas(caso: Annotated[GenerarAlertas, Depends(caso_alertas)]):
    return a_alertas(await caso.ejecutar())
