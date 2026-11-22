from datetime import timedelta

import pytest

from app.dominio.modelos import Prioridad
from app.dominio.reglas import (
    ReglasAlertas,
    distancia_m,
    esta_desactualizado,
    minutos_sin_actualizar,
    prioridad_por_bateria,
    puntaje,
)
from tests.fakes import AHORA


def test_el_puntaje_es_distancia_menos_dos_veces_la_bateria():
    assert puntaje(150, 81) == -12
    assert puntaje(112, 61) == -10
    assert puntaje(0, 0) == 0


def test_a_igual_distancia_gana_el_de_mas_bateria():
    assert puntaje(100, 90) < puntaje(100, 30)


def test_a_igual_bateria_gana_el_mas_cercano():
    assert puntaje(50, 60) < puntaje(300, 60)


@pytest.mark.parametrize(
    ("bateria", "prioridad"),
    [(0, Prioridad.ALTA), (9, Prioridad.ALTA), (10, Prioridad.MEDIA), (14, Prioridad.MEDIA)],
)
def test_prioridad_por_bateria_alta_solo_por_debajo_de_10(bateria, prioridad):
    assert prioridad_por_bateria(bateria, ReglasAlertas()) == prioridad


def test_minutos_sin_actualizar_redondea_hacia_abajo_y_nunca_es_negativo():
    assert minutos_sin_actualizar(AHORA, AHORA - timedelta(minutes=90, seconds=59)) == 90
    assert minutos_sin_actualizar(AHORA, AHORA + timedelta(minutes=5)) == 0


def test_desactualizado_es_estrictamente_mas_de_dos_horas():
    r = ReglasAlertas()
    assert not esta_desactualizado(AHORA, AHORA - timedelta(hours=2), r)
    assert esta_desactualizado(AHORA, AHORA - timedelta(hours=2, seconds=1), r)


def test_el_umbral_de_horas_es_configurable():
    r = ReglasAlertas(horas_sin_actualizar=0.5)
    assert esta_desactualizado(AHORA, AHORA - timedelta(minutes=31), r)


def test_distancia_haversine_coincide_con_la_de_mongodb():
    # 0,00135° de longitud a la latitud de Bogotá son ~150 m (el dato que devuelve el CRUD para veh-0014).
    assert distancia_m(4.7110, -74.0721, 4.7110, -74.07345) == pytest.approx(150, abs=1)
