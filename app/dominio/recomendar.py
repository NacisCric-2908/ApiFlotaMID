"""Caso de uso: recomendar los mejores vehículos cerca de un punto.

Reglas del documento de requisitos, en orden:
 1. Busca vehículos `disponible` dentro del radio (500 m por defecto).
 2. Descarta los de batería menor al mínimo (25 %).
 3. Consulta a Viajes y zonas si cada candidato está en una zona prohibida y lo descarta si es así.
 4. Ordena por `puntaje = distancia - batería * 2` (menor es mejor) y devuelve los 3 mejores.
 5. Si no queda ninguno: lista vacía con un motivo.
 6. Si Viajes y zonas no responde: error (el MID responde 503); no se recomienda sin validar las zonas.
"""

from app.dominio.modelos import Candidato, MotivoVacio, Recomendacion
from app.dominio.puertos import VehiculosPort, ZonasPort
from app.dominio.reglas import ReglasRecomendacion, distancia_m, puntaje
from app.dominio.zonas import ids_en_zona_prohibida


class RecomendarVehiculo:
    def __init__(self, vehiculos: VehiculosPort, zonas: ZonasPort, reglas: ReglasRecomendacion | None = None):
        self.vehiculos = vehiculos
        self.zonas = zonas
        self.reglas = reglas or ReglasRecomendacion()

    async def ejecutar(self, lat: float, lng: float, tipo: str | None = None) -> Recomendacion:
        r = self.reglas
        cercanos = await self.vehiculos.buscar_cercanos(lat, lng, r.radio_m, tipo, r.bateria_minima)

        # El CRUD ya filtra, pero las reglas son del MID: se aplican aquí también, para no depender de que
        # otro servicio las cumpla.
        con_distancia = [(v, v.distancia_m if v.distancia_m is not None else distancia_m(lat, lng, v.lat, v.lng)) for v in cercanos]
        elegibles = [
            (v, d)
            for v, d in con_distancia
            if v.estado == "disponible" and d <= r.radio_m and (tipo is None or v.tipo == tipo)
        ]
        con_bateria = [(v, d) for v, d in elegibles if v.bateria_pct >= r.bateria_minima]
        if not con_bateria:
            return Recomendacion(candidatos=(), motivo=MotivoVacio.SIN_VEHICULOS_CERCANOS)

        prohibidos = await ids_en_zona_prohibida(self.zonas, [v for v, _ in con_bateria], r.concurrencia_zonas)
        permitidos = [(v, d) for v, d in con_bateria if v.id not in prohibidos]
        if not permitidos:
            return Recomendacion(candidatos=(), motivo=MotivoVacio.TODOS_EN_ZONA_PROHIBIDA)

        candidatos = [Candidato(vehiculo=v, distancia_m=d, puntaje=puntaje(d, v.bateria_pct)) for v, d in permitidos]
        # Desempate determinista: a igual puntaje, el más cercano y luego por id.
        candidatos.sort(key=lambda c: (c.puntaje, c.distancia_m, c.vehiculo.id))
        return Recomendacion(candidatos=tuple(candidatos[: r.max_resultados]))
