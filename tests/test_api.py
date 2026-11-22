import pytest

from app.dominio.errores import ServicioNoDisponible
from tests.aplicacion import cliente_api
from tests.fakes import VehiculosFalso, ZonasFalso, vehiculo

RECOMENDAR = "/recomendaciones/vehiculo"
ALERTAS = "/flota/alertas"
PUNTO = {"lat": 4.7110, "lng": -74.0721}


# ---------- seguridad y salud ----------
async def test_health_es_publico():
    async with cliente_api(secreto=None) as c:
        r = await c.get("/health")
    assert r.status_code == 200 and r.json() == {"estado": "ok"}


@pytest.mark.parametrize("ruta", [RECOMENDAR, ALERTAS])
@pytest.mark.parametrize("secreto", [None, "otro"])
async def test_sin_la_cabecera_secreta_del_gateway_responde_401(ruta, secreto):
    async with cliente_api(secreto=secreto) as c:
        r = await c.get(ruta, params=PUNTO)
    assert r.status_code == 401 and r.json()["codigo"] == "gateway_no_autorizado"


async def test_una_ruta_inexistente_usa_el_formato_de_error_comun():
    async with cliente_api() as c:
        r = await c.get("/no-existe")
    assert r.status_code == 404 and set(r.json()) == {"codigo", "mensaje", "detalle"}
    assert r.json()["codigo"] == "no_encontrado"


async def test_un_metodo_no_permitido_responde_405():
    async with cliente_api() as c:
        r = await c.post(RECOMENDAR)
    assert r.status_code == 405 and r.json()["codigo"] == "metodo_no_permitido"


async def test_un_error_inesperado_responde_500_con_el_formato_comun():
    class Roto:
        async def buscar_cercanos(self, *a):
            raise RuntimeError("boom")

    async with cliente_api(vehiculos=Roto()) as c:
        r = await c.get(RECOMENDAR, params=PUNTO)
    assert r.status_code == 500 and r.json()["codigo"] == "error_interno"
    assert "boom" not in r.text  # no se filtran detalles internos


# ---------- recomendaciones ----------
async def test_recomienda_los_mejores_con_distancia_bateria_y_puntaje():
    a = vehiculo("a", bateria=81, distancia=150.04)
    b = vehiculo("b", bateria=61, distancia=112.0, lat=4.7119)
    async with cliente_api(VehiculosFalso(cercanos=[b, a])) as c:
        r = await c.get(RECOMENDAR, params=PUNTO)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 2 and "motivo" not in cuerpo
    primero = cuerpo["recomendaciones"][0]
    assert primero == {
        "vehiculoId": "a", "tipo": "scooter", "distanciaMetros": 150.0, "bateriaPct": 81, "puntaje": -12.0,
        "ubicacion": {"type": "Point", "coordinates": [-74.0721, 4.711]},
    }  # fmt: skip
    assert [x["vehiculoId"] for x in cuerpo["recomendaciones"]] == ["a", "b"]


async def test_sin_candidatos_responde_200_con_lista_vacia_y_motivo():
    async with cliente_api(VehiculosFalso(cercanos=[])) as c:
        r = await c.get(RECOMENDAR, params=PUNTO)
    assert r.status_code == 200
    assert r.json() == {"recomendaciones": [], "total": 0, "motivo": "sin_vehiculos_cercanos"}


async def test_todos_en_zona_prohibida_se_explica_con_el_motivo():
    v = vehiculo("a")
    async with cliente_api(VehiculosFalso(cercanos=[v]), ZonasFalso([v])) as c:
        r = await c.get(RECOMENDAR, params=PUNTO)
    assert r.status_code == 200 and r.json()["motivo"] == "todos_en_zona_prohibida"


async def test_el_tipo_se_pasa_al_servicio_de_vehiculos():
    crud = VehiculosFalso()
    async with cliente_api(crud) as c:
        await c.get(RECOMENDAR, params={**PUNTO, "tipo": "bicicleta"})
    assert crud.llamadas[0]["tipo"] == "bicicleta" and crud.llamadas[0]["radio_m"] == 500


@pytest.mark.parametrize(
    "params",
    [
        {"lng": -74.0},
        {"lat": 4.7},
        {"lat": 91, "lng": -74.0},
        {"lat": 4.7, "lng": -181},
        {"lat": "abc", "lng": -74.0},
        {**PUNTO, "tipo": "moto"},
    ],
)
async def test_parametros_invalidos_responden_400(params):
    async with cliente_api() as c:
        r = await c.get(RECOMENDAR, params=params)
    assert r.status_code == 400
    assert r.json()["codigo"] == "solicitud_invalida"
    assert all(set(e) == {"campo", "mensaje"} for e in r.json()["detalle"]["errores"])


async def test_si_viajes_y_zonas_no_responde_la_recomendacion_es_503():
    caida = ServicioNoDisponible("viajes-zonas", "ReadTimeout")
    async with cliente_api(VehiculosFalso(cercanos=[vehiculo("a")]), ZonasFalso(error=caida)) as c:
        r = await c.get(RECOMENDAR, params=PUNTO)
    assert r.status_code == 503
    assert r.json()["codigo"] == "servicio_no_disponible"
    assert r.json()["detalle"] == {"servicio": "viajes-zonas", "motivo": "ReadTimeout"}
    assert "zonas" in r.json()["mensaje"]


async def test_si_el_servicio_de_vehiculos_esta_caido_es_503():
    crud = VehiculosFalso(error=ServicioNoDisponible("flota-crud", "ConnectError"))
    async with cliente_api(crud) as c:
        r = await c.get(RECOMENDAR, params=PUNTO)
    assert r.status_code == 503 and r.json()["detalle"]["servicio"] == "flota-crud"


# ---------- alertas ----------
async def test_lista_las_alertas_ordenadas_con_todos_sus_campos():
    bajo = vehiculo("bajo", bateria=5, minutos_sin_actualizar=30)
    viejo = vehiculo("viejo", minutos_sin_actualizar=200, lat=4.7101)
    async with cliente_api(VehiculosFalso(todos=[viejo, bajo])) as c:
        r = await c.get(ALERTAS)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 2 and cuerpo["advertencias"] == []
    assert [(a["vehiculoId"], a["tipoAlerta"], a["prioridad"]) for a in cuerpo["alertas"]] == [
        ("bajo", "bateria_baja", "alta"),
        ("viejo", "sin_actualizar", "media"),
    ]
    a = cuerpo["alertas"][0]
    assert set(a) >= {"vehiculoId", "tipoAlerta", "prioridad", "detalle", "bateriaPct", "ubicacion", "actualizadoEn", "minutosSinActualizar", "estado", "tipo"}
    assert a["minutosSinActualizar"] == 30 and a["bateriaPct"] == 5 and a["estado"] == "disponible"


async def test_una_flota_sin_problemas_devuelve_lista_vacia():
    async with cliente_api(VehiculosFalso(todos=[vehiculo()])) as c:
        r = await c.get(ALERTAS)
    assert r.status_code == 200 and r.json() == {"alertas": [], "total": 0, "advertencias": []}


async def test_si_viajes_y_zonas_no_responde_las_alertas_siguen_con_una_advertencia():
    caida = ServicioNoDisponible("viajes-zonas", "http_503")
    async with cliente_api(VehiculosFalso(todos=[vehiculo("bajo", bateria=5)]), ZonasFalso(error=caida)) as c:
        r = await c.get(ALERTAS)
    assert r.status_code == 200
    assert r.json()["advertencias"] == ["zonas_no_verificadas"] and r.json()["total"] == 1


async def test_las_alertas_con_el_servicio_de_vehiculos_caido_son_503():
    crud = VehiculosFalso(error=ServicioNoDisponible("flota-crud", "http_503"))
    async with cliente_api(crud) as c:
        r = await c.get(ALERTAS)
    assert r.status_code == 503 and r.json()["detalle"]["servicio"] == "flota-crud"
