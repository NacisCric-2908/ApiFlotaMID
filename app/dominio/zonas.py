import asyncio
from collections.abc import Sequence

from app.dominio.errores import ServicioNoDisponible
from app.dominio.modelos import Vehiculo
from app.dominio.puertos import ZonasPort


async def ids_en_zona_prohibida(zonas: ZonasPort, vehiculos: Sequence[Vehiculo], concurrencia: int) -> set[str]:
    """Pregunta a Viajes y zonas por cada vehículo, en paralelo pero con un tope de consultas simultáneas.

    Si alguna consulta falla se lanza el error: no se puede afirmar nada de un vehículo sin saber en qué zona está.
    """
    semaforo = asyncio.Semaphore(max(1, concurrencia))

    async def consultar(v: Vehiculo) -> tuple[str, bool]:
        async with semaforo:
            return v.id, await zonas.esta_en_zona_prohibida(v.lat, v.lng)

    resultados = await asyncio.gather(*(consultar(v) for v in vehiculos), return_exceptions=True)
    fallos = [r for r in resultados if isinstance(r, BaseException)]
    if fallos:
        # Se prefiere el error conocido (para responder 503) a uno inesperado.
        raise next((f for f in fallos if isinstance(f, ServicioNoDisponible)), fallos[0])
    return {id_ for id_, prohibido in resultados if prohibido}  # type: ignore[misc]
