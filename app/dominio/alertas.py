"""Caso de uso: alertas para el equipo operativo.

Un vehículo requiere atención si:
 - su batería es menor a 15 % (prioridad alta si es menor a 10 %, media si no),
 - está en una zona prohibida (prioridad alta), o
 - su ubicación no se actualiza hace más de 2 horas (prioridad media).

Se genera **una alerta por cada condición** que cumple un vehículo (campo `tipoAlerta`): uno con batería baja
y en zona prohibida aparece dos veces. Solo se evalúan los estados configurados (por defecto `disponible`).
La lista sale ordenada por prioridad y luego por tiempo sin actualizar (el más antiguo primero).

Si Viajes y zonas no responde, no se pierde todo: se devuelven las alertas de batería e inactividad y una
advertencia `zonas_no_verificadas`. (A diferencia de la recomendación, aquí un resultado parcial sirve.)
"""

from app.dominio.errores import ServicioNoDisponible
from app.dominio.modelos import Alerta, Prioridad, ResultadoAlertas, TipoAlerta
from app.dominio.puertos import RelojPort, VehiculosPort, ZonasPort
from app.dominio.reglas import (
    ReglasAlertas,
    esta_desactualizado,
    minutos_sin_actualizar,
    prioridad_por_bateria,
)
from app.dominio.zonas import ids_en_zona_prohibida

ZONAS_NO_VERIFICADAS = "zonas_no_verificadas"


class GenerarAlertas:
    def __init__(self, vehiculos: VehiculosPort, zonas: ZonasPort, reloj: RelojPort, reglas: ReglasAlertas | None = None):
        self.vehiculos = vehiculos
        self.zonas = zonas
        self.reloj = reloj
        self.reglas = reglas or ReglasAlertas()

    async def ejecutar(self) -> ResultadoAlertas:
        r = self.reglas
        evaluables = [v for v in await self.vehiculos.listar_todos() if v.estado in r.estados]

        advertencias: list[str] = []
        prohibidos: set[str] = set()
        try:
            prohibidos = await ids_en_zona_prohibida(self.zonas, evaluables, r.concurrencia_zonas)
        except ServicioNoDisponible:
            advertencias.append(ZONAS_NO_VERIFICADAS)

        ahora = self.reloj.ahora()
        alertas: list[Alerta] = []
        for v in evaluables:
            minutos = minutos_sin_actualizar(ahora, v.actualizado_en)
            if v.bateria_pct < r.bateria_alerta:
                alertas.append(
                    Alerta(v, TipoAlerta.BATERIA_BAJA, prioridad_por_bateria(v.bateria_pct, r),
                           f"Batería al {v.bateria_pct} %", minutos)
                )
            if v.id in prohibidos:
                alertas.append(
                    Alerta(v, TipoAlerta.ZONA_PROHIBIDA, Prioridad.ALTA, "Está en una zona prohibida", minutos)
                )
            if esta_desactualizado(ahora, v.actualizado_en, r):
                alertas.append(
                    Alerta(v, TipoAlerta.SIN_ACTUALIZAR, Prioridad.MEDIA,
                           f"Sin actualizar su ubicación hace {minutos} min", minutos)
                )

        orden_prioridad = {Prioridad.ALTA: 0, Prioridad.MEDIA: 1}
        alertas.sort(key=lambda a: (orden_prioridad[a.prioridad], -a.minutos_sin_actualizar, a.vehiculo.id, a.tipo))
        return ResultadoAlertas(alertas=tuple(alertas), advertencias=tuple(advertencias))
