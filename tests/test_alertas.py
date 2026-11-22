import pytest

from app.dominio.alertas import ZONAS_NO_VERIFICADAS, GenerarAlertas
from app.dominio.errores import ServicioNoDisponible
from app.dominio.modelos import Prioridad, TipoAlerta
from app.dominio.reglas import ReglasAlertas
from tests.fakes import RelojFalso, VehiculosFalso, ZonasFalso, vehiculo


async def alertas(todos, prohibidos=(), error_zonas=None, error_crud=None, reglas=None):
    caso = GenerarAlertas(VehiculosFalso(todos=todos, error=error_crud), ZonasFalso(prohibidos, error_zonas), RelojFalso(), reglas)
    return await caso.ejecutar()


def resumen(resultado):
    return [(a.vehiculo.id, a.tipo.value, a.prioridad.value) for a in resultado.alertas]


async def test_bateria_menor_a_15_es_alerta_media_y_menor_a_10_es_alta():
    r = await alertas([vehiculo("b14", bateria=14), vehiculo("b9", bateria=9, lat=4.7101)])
    assert resumen(r) == [("b9", "bateria_baja", "alta"), ("b14", "bateria_baja", "media")]


@pytest.mark.parametrize("bateria", [15, 16, 80])
async def test_con_15_o_mas_no_hay_alerta_de_bateria(bateria):
    assert (await alertas([vehiculo(bateria=bateria)])).alertas == ()


async def test_el_limite_de_10_es_media_porque_alta_es_estrictamente_menor():
    r = await alertas([vehiculo("justo", bateria=10)])
    assert resumen(r) == [("justo", "bateria_baja", "media")]


async def test_zona_prohibida_es_prioridad_alta():
    v = vehiculo("z", bateria=90)
    assert resumen(await alertas([v], prohibidos=[v])) == [("z", "zona_prohibida", "alta")]


async def test_mas_de_dos_horas_sin_actualizar_es_prioridad_media():
    r = await alertas([vehiculo("viejo", minutos_sin_actualizar=181)])
    assert resumen(r) == [("viejo", "sin_actualizar", "media")]
    assert r.alertas[0].minutos_sin_actualizar == 181


async def test_exactamente_dos_horas_todavia_no_es_alerta():
    assert (await alertas([vehiculo(minutos_sin_actualizar=120)])).alertas == ()


async def test_un_vehiculo_con_varias_condiciones_aparece_una_vez_por_cada_una():
    v = vehiculo("todo", bateria=5, minutos_sin_actualizar=200)
    r = await alertas([v], prohibidos=[v])
    assert sorted(a.tipo.value for a in r.alertas) == ["bateria_baja", "sin_actualizar", "zona_prohibida"]
    assert {a.vehiculo.id for a in r.alertas} == {"todo"}


async def test_ordena_por_prioridad_y_luego_por_tiempo_sin_actualizar_el_mas_antiguo_primero():
    a = vehiculo("a", bateria=12, minutos_sin_actualizar=10, lat=4.7101)  # media, 10 min
    b = vehiculo("b", bateria=5, minutos_sin_actualizar=30, lat=4.7102)  # alta, 30 min
    c = vehiculo("c", bateria=5, minutos_sin_actualizar=90, lat=4.7103)  # alta, 90 min
    d = vehiculo("d", bateria=13, minutos_sin_actualizar=60, lat=4.7104)  # media, 60 min
    assert [x.vehiculo.id for x in (await alertas([a, b, c, d])).alertas] == ["c", "b", "d", "a"]


async def test_solo_evalua_los_vehiculos_disponibles():
    en_viaje = vehiculo("viaje", estado="en_viaje", bateria=1, minutos_sin_actualizar=999)
    taller = vehiculo("taller", estado="mantenimiento", bateria=1, lat=4.7101)
    assert (await alertas([en_viaje, taller])).alertas == ()


async def test_los_estados_que_se_evaluan_son_configurables():
    taller = vehiculo("taller", estado="mantenimiento", bateria=1)
    r = await alertas([taller], reglas=ReglasAlertas(estados=frozenset({"disponible", "mantenimiento"})))
    assert resumen(r) == [("taller", "bateria_baja", "alta")]


async def test_si_viajes_y_zonas_no_responde_devuelve_las_demas_alertas_con_una_advertencia():
    caida = ServicioNoDisponible("viajes-zonas", "ReadTimeout")
    r = await alertas([vehiculo("b", bateria=5), vehiculo("ok", lat=4.7101)], error_zonas=caida)
    assert resumen(r) == [("b", "bateria_baja", "alta")]
    assert r.advertencias == (ZONAS_NO_VERIFICADAS,)


async def test_sin_problemas_no_hay_advertencias():
    r = await alertas([vehiculo()])
    assert r.alertas == () and r.advertencias == ()


async def test_si_el_servicio_de_vehiculos_no_responde_se_propaga_el_error():
    with pytest.raises(ServicioNoDisponible) as e:
        await alertas([], error_crud=ServicioNoDisponible("flota-crud", "http_503"))
    assert e.value.servicio == "flota-crud"


async def test_no_consulta_zonas_de_los_vehiculos_que_no_evalua():
    zonas = ZonasFalso()
    todos = [vehiculo("a"), vehiculo("viaje", estado="en_viaje", lat=4.7101)]
    await GenerarAlertas(VehiculosFalso(todos=todos), zonas, RelojFalso()).ejecutar()
    assert len(zonas.consultas) == 1
