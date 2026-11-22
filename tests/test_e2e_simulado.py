"""El MID completo, con sus adaptadores HTTP reales, hablando con el simulador de los otros servicios.

Es lo más parecido a la demostración que se puede probar sin los servicios reales: pasa por el cliente HTTP, el
token del gateway, la paginación y las reglas. Los resultados esperados son los de docs/semilla.md del CRUD de Flota.
"""

from contextlib import asynccontextmanager

import httpx
import pytest

from app.adaptadores.salida.token import TokenGateway
from app.adaptadores.salida.vehiculos_http import VehiculosHttp
from app.adaptadores.salida.zonas_http import ZonasHttp
from simuladores.upstream import crear_simulador
from tests.aplicacion import cliente_api
from tests.fakes import AHORA, RelojFalso

CENTRO = {"lat": 4.7110, "lng": -74.0721}


@asynccontextmanager
async def mid_con_simulador(client_secret="s-mid", crud_secret="s-crud", reloj=None):
    sim = crear_simulador(ahora=AHORA, crud_secret="s-crud", client_id="mid-flota", client_secret="s-mid")
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=sim))
    vehiculos = VehiculosHttp(http, "http://sim", crud_secret, reintentos=0, backoff_s=0)
    tokens = TokenGateway(http, "http://sim/token", "mid-flota", client_secret, "zonas:leer", reintentos=0, backoff_s=0)
    zonas = ZonasHttp(http, "http://sim", "/viajes/zonas/verificar", tokens, reintentos=0, backoff_s=0)
    try:
        async with cliente_api(vehiculos, zonas, reloj or RelojFalso(AHORA)) as cliente:
            yield cliente, sim
    finally:
        await http.aclose()


async def test_la_recomendacion_desde_el_centro_es_la_documentada():
    async with mid_con_simulador() as (c, sim):
        r = await c.get("/recomendaciones/vehiculo", params=CENTRO)
    assert r.status_code == 200
    top = [(x["vehiculoId"], x["distanciaMetros"], x["bateriaPct"], x["puntaje"]) for x in r.json()["recomendaciones"]]
    assert [t[0] for t in top] == ["veh-0014", "veh-0022", "veh-0008"]  # mejor puntaje primero
    assert [t[1] for t in top] == pytest.approx([150, 112, 180], abs=1)
    assert [t[2] for t in top] == [81, 61, 73]
    assert [t[3] for t in top] == pytest.approx([-12, -10, 34], abs=1)


async def test_el_vehiculo_mas_cercano_se_descarta_por_estar_en_la_zona_prohibida():
    async with mid_con_simulador() as (c, _):
        # veh-0016 (59 %, a ~50 m) sería candidato, pero está dentro de «Prohibida Centro».
        ids = {x["vehiculoId"] for x in (await c.get("/recomendaciones/vehiculo", params=CENTRO)).json()["recomendaciones"]}
    assert "veh-0016" not in ids


async def test_nunca_recomienda_un_vehiculo_con_poca_bateria_ni_ocupado():
    async with mid_con_simulador() as (c, sim):
        r = await c.get("/recomendaciones/vehiculo", params={**CENTRO, "tipo": "scooter"})
    por_id = {v["id"]: v for v in sim.state.vehiculos}
    for x in r.json()["recomendaciones"]:
        v = por_id[x["vehiculoId"]]
        assert v["bateriaPct"] >= 25 and v["estado"] == "disponible" and v["tipo"] == "scooter"


async def test_lejos_de_los_vehiculos_responde_lista_vacia_con_motivo():
    async with mid_con_simulador() as (c, _):
        r = await c.get("/recomendaciones/vehiculo", params={"lat": 4.60, "lng": -74.07})
    assert r.status_code == 200 and r.json() == {"recomendaciones": [], "total": 0, "motivo": "sin_vehiculos_cercanos"}


async def test_el_token_se_pide_una_sola_vez_aunque_haya_muchas_consultas_de_zonas():
    async with mid_con_simulador() as (c, sim):
        await c.get("/recomendaciones/vehiculo", params=CENTRO)
        await c.get("/flota/alertas")
    assert sim.state.tokens_emitidos == 1


async def test_si_el_gateway_revoca_el_token_el_mid_pide_otro_y_sigue():
    async with mid_con_simulador() as (c, sim):
        assert (await c.get("/recomendaciones/vehiculo", params=CENTRO)).status_code == 200
        sim.state.tokens_vigentes.clear()  # el token deja de valer
        r = await c.get("/recomendaciones/vehiculo", params=CENTRO)
    assert r.status_code == 200 and sim.state.tokens_emitidos == 2


async def test_las_alertas_con_los_datos_semilla_son_las_esperadas():
    async with mid_con_simulador() as (c, _):
        r = await c.get("/flota/alertas")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["advertencias"] == []
    resumen = [(a["vehiculoId"], a["tipoAlerta"], a["prioridad"], a["minutosSinActualizar"]) for a in cuerpo["alertas"]]
    assert resumen == [
        ("veh-0016", "zona_prohibida", "alta", 15),  # en la zona prohibida
        ("veh-0015", "bateria_baja", "alta", 14),  # 9 % de batería
        ("veh-0021", "sin_actualizar", "media", 200),  # 3 h y 20 min sin actualizar
        ("veh-0008", "sin_actualizar", "media", 187),
        ("veh-0019", "bateria_baja", "media", 18),  # 14 %
        ("veh-0009", "bateria_baja", "media", 8),  # 12 %
    ]


async def test_si_viajes_y_zonas_esta_caido_la_recomendacion_es_503_y_las_alertas_degradan():
    async with mid_con_simulador() as (c, sim):
        sim.state.zonas_caidas = True
        r = await c.get("/recomendaciones/vehiculo", params=CENTRO)
        assert r.status_code == 503
        assert r.json()["detalle"]["servicio"] == "viajes-zonas"
        a = await c.get("/flota/alertas")
    assert a.status_code == 200
    assert a.json()["advertencias"] == ["zonas_no_verificadas"]
    assert {x["tipoAlerta"] for x in a.json()["alertas"]} == {"bateria_baja", "sin_actualizar"}


async def test_con_flota_apagada_la_recomendacion_es_503():
    """Paso 10 de la demostración: apagar el servicio de Flota y repetir la recomendación."""
    async with mid_con_simulador() as (c, sim):
        sim.state.crud_caido = True
        r = await c.get("/recomendaciones/vehiculo", params=CENTRO)
    assert r.status_code == 503 and r.json()["detalle"]["servicio"] == "flota-crud"


async def test_si_las_credenciales_del_mid_no_valen_el_error_dice_que_es_el_token():
    async with mid_con_simulador(client_secret="equivocado") as (c, _):
        r = await c.get("/recomendaciones/vehiculo", params=CENTRO)
    assert r.status_code == 503
    assert r.json()["detalle"] == {"servicio": "gateway-token", "motivo": "http_401"}


async def test_si_el_secreto_del_crud_esta_mal_configurado_el_error_lo_dice():
    async with mid_con_simulador(crud_secret="equivocado") as (c, _):
        r = await c.get("/recomendaciones/vehiculo", params=CENTRO)
    assert r.status_code == 503
    assert r.json()["detalle"] == {"servicio": "flota-crud", "motivo": "http_401"}
