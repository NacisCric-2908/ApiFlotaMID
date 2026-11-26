import pytest

from app.dominio.errores import ServicioNoDisponible
from app.dominio.modelos import MotivoVacio
from app.dominio.recomendar import RecomendarVehiculo
from app.dominio.reglas import ReglasRecomendacion
from tests.fakes import VehiculosFalso, ZonasFalso, vehiculo

LAT, LNG = 4.7110, -74.0721


async def recomendar(cercanos, prohibidos=(), tipo=None, reglas=None, error_zonas=None):
    caso = RecomendarVehiculo(VehiculosFalso(cercanos=cercanos), ZonasFalso(prohibidos, error_zonas), reglas)
    return await caso.ejecutar(LAT, LNG, tipo)


async def test_ordena_por_puntaje_y_devuelve_los_mejores():
    # puntajes: a = 150-162 = -12, b = 112-122 = -10, c = 180-146 = 34, d = 300-100 = 200
    a = vehiculo("a", bateria=81, distancia=150)
    b = vehiculo("b", bateria=61, distancia=112, lat=4.7119)
    c = vehiculo("c", bateria=73, distancia=180, lat=4.7101)
    d = vehiculo("d", bateria=50, distancia=300, lat=4.7083)
    r = await recomendar([d, c, b, a])
    assert [x.vehiculo.id for x in r.candidatos] == ["a", "b", "c"]
    assert [x.puntaje for x in r.candidatos] == [-12, -10, 34]
    assert r.motivo is None


async def test_un_vehiculo_con_20_por_ciento_de_bateria_nunca_se_recomienda():
    poca = vehiculo("poca", bateria=20, distancia=10)
    ok = vehiculo("ok", bateria=40, distancia=400, lat=4.7083)
    r = await recomendar([poca, ok])
    assert [x.vehiculo.id for x in r.candidatos] == ["ok"]


async def test_el_minimo_de_bateria_es_inclusivo():
    justo = vehiculo("justo", bateria=25)
    debajo = vehiculo("debajo", bateria=24, lat=4.7101)
    r = await recomendar([justo, debajo])
    assert [x.vehiculo.id for x in r.candidatos] == ["justo"]


async def test_solo_recomienda_vehiculos_disponibles():
    r = await recomendar([vehiculo("viaje", estado="en_viaje"), vehiculo("taller", estado="mantenimiento", lat=4.7101)])
    assert r.candidatos == () and r.motivo == MotivoVacio.SIN_VEHICULOS_CERCANOS


async def test_descarta_los_que_estan_fuera_del_radio_aunque_el_crud_los_devuelva():
    lejos = vehiculo("lejos", distancia=501)
    cerca = vehiculo("cerca", distancia=500, lat=4.7101)
    r = await recomendar([lejos, cerca])
    assert [x.vehiculo.id for x in r.candidatos] == ["cerca"]


async def test_descarta_los_que_estan_en_zona_prohibida():
    prohibido = vehiculo("prohibido", bateria=99, distancia=10)
    libre = vehiculo("libre", bateria=40, distancia=300, lat=4.7083)
    r = await recomendar([prohibido, libre], prohibidos=[prohibido])
    assert [x.vehiculo.id for x in r.candidatos] == ["libre"]


async def test_sin_vehiculos_cercanos_responde_lista_vacia_con_motivo():
    r = await recomendar([])
    assert r.candidatos == () and r.motivo == MotivoVacio.SIN_VEHICULOS_CERCANOS


async def test_si_todos_tienen_poca_bateria_el_motivo_es_sin_vehiculos_cercanos():
    r = await recomendar([vehiculo("a", bateria=10), vehiculo("b", bateria=24, lat=4.7101)])
    assert r.candidatos == () and r.motivo == MotivoVacio.SIN_VEHICULOS_CERCANOS


async def test_si_todos_estan_en_zona_prohibida_el_motivo_lo_dice():
    a, b = vehiculo("a"), vehiculo("b", lat=4.7101)
    r = await recomendar([a, b], prohibidos=[a, b])
    assert r.candidatos == () and r.motivo == MotivoVacio.TODOS_EN_ZONA_PROHIBIDA


async def test_si_viajes_y_zonas_no_responde_no_se_recomienda_nada():
    caida = ServicioNoDisponible("viajes-zonas", "ReadTimeout")
    with pytest.raises(ServicioNoDisponible) as e:
        await recomendar([vehiculo("a")], error_zonas=caida)
    assert e.value.servicio == "viajes-zonas"


async def test_si_el_servicio_de_vehiculos_no_responde_se_propaga_el_error():
    caso = RecomendarVehiculo(VehiculosFalso(error=ServicioNoDisponible("flota-crud", "http_503")), ZonasFalso())
    with pytest.raises(ServicioNoDisponible) as e:
        await caso.ejecutar(LAT, LNG)
    assert e.value.servicio == "flota-crud"


async def test_no_consulta_zonas_si_ningun_candidato_pasa_los_filtros_previos():
    zonas = ZonasFalso()
    caso = RecomendarVehiculo(VehiculosFalso(cercanos=[vehiculo("a", bateria=5)]), zonas)
    await caso.ejecutar(LAT, LNG)
    assert zonas.consultas == []


async def test_consulta_las_zonas_de_cada_candidato_una_vez():
    zonas = ZonasFalso()
    cercanos = [vehiculo(f"v{i}", lat=4.7 + i / 1000) for i in range(5)]
    await RecomendarVehiculo(VehiculosFalso(cercanos=cercanos), zonas).ejecutar(LAT, LNG)
    assert len(zonas.consultas) == 5


async def test_limita_las_consultas_simultaneas_a_viajes_y_zonas():
    zonas = ZonasFalso()
    cercanos = [vehiculo(f"v{i}", lat=4.7 + i / 1000) for i in range(12)]
    caso = RecomendarVehiculo(VehiculosFalso(cercanos=cercanos), zonas, ReglasRecomendacion(concurrencia_zonas=3))
    await caso.ejecutar(LAT, LNG)
    assert zonas.maximo_simultaneas == 3


async def test_pide_al_crud_los_parametros_de_las_reglas():
    crud = VehiculosFalso(cercanos=[vehiculo("a")])
    await RecomendarVehiculo(crud, ZonasFalso()).ejecutar(LAT, LNG, "bicicleta")
    assert crud.llamadas == [{"lat": LAT, "lng": LNG, "radio_m": 500, "tipo": "bicicleta", "bateria_min": 25}]


async def test_filtra_por_tipo_aunque_el_crud_devuelva_otros():
    scooter, bici = vehiculo("s", tipo="scooter"), vehiculo("b", tipo="bicicleta", lat=4.7101)
    r = await recomendar([scooter, bici], tipo="bicicleta")
    assert [x.vehiculo.id for x in r.candidatos] == ["b"]


async def test_el_radio_y_el_minimo_son_configurables():
    cerca = vehiculo("cerca", distancia=100, bateria=40)
    r = await recomendar([cerca], reglas=ReglasRecomendacion(radio_m=50))
    assert r.motivo == MotivoVacio.SIN_VEHICULOS_CERCANOS
    r = await recomendar([cerca], reglas=ReglasRecomendacion(bateria_minima=50))
    assert r.motivo == MotivoVacio.SIN_VEHICULOS_CERCANOS


async def test_el_empate_se_resuelve_por_distancia_y_luego_por_id():
    # mismo puntaje (0): 100 m con 50 % y 40 m con 20 %... pero 20 % no pasa; se usa 60 m con 30 % y 100 m con 50 %
    a = vehiculo("b", bateria=50, distancia=100)
    b = vehiculo("a", bateria=30, distancia=60, lat=4.7101)
    r = await recomendar([a, b])
    assert [x.puntaje for x in r.candidatos] == [0, 0]
    assert [x.vehiculo.id for x in r.candidatos] == ["a", "b"]  # a es más cercano


async def test_calcula_la_distancia_si_el_crud_no_la_trae():
    sin_distancia = vehiculo("a", distancia=None, lat=4.7110, lng=-74.07345)  # ~150 m del punto
    r = await recomendar([sin_distancia])
    assert r.candidatos[0].distancia_m == pytest.approx(150, abs=1)
