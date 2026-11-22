import logging
from datetime import timezone

import httpx
import pytest

from app.adaptadores.salida.vehiculos_http import VehiculosHttp
from app.dominio.errores import ServicioNoDisponible
from tests.fakes import ITEM_CRUD, Registro, cliente_simulado


def pagina(items, total=None, **extra):
    return httpx.Response(200, json={"items": items, "pagina": 1, "tamano": 100, "total": len(items) if total is None else total, **extra})


def crear(http, **kw):
    return VehiculosHttp(http, "http://crud:8000/", "secreto-del-crud", reintentos=2, backoff_s=0, **kw)


async def test_busca_cercanos_con_los_filtros_y_la_cabecera_secreta():
    reg = Registro(pagina([ITEM_CRUD]))
    async with cliente_simulado(reg) as http:
        await crear(http).buscar_cercanos(4.711, -74.0721, 500.0, "bicicleta", 25)
    (p,) = reg.peticiones
    assert (p.url.host, p.url.path) == ("crud", "/vehiculos")
    assert dict(p.url.params) == {
        "lat": "4.711", "lng": "-74.0721", "radioMetros": "500.0", "estado": "disponible",
        "tipo": "bicicleta", "bateriaMin": "25", "pagina": "1", "tamano": "100",
    }  # fmt: skip
    assert p.headers["x-gateway-secret"] == "secreto-del-crud"


async def test_omite_los_filtros_que_no_se_pidieron():
    reg = Registro(pagina([]))
    async with cliente_simulado(reg) as http:
        await crear(http).buscar_cercanos(4.7, -74.0, 500, None, None)
    assert {"tipo", "bateriaMin"}.isdisjoint(reg.peticiones[0].url.params)


async def test_traduce_la_respuesta_real_del_crud_al_modelo_del_dominio():
    async with cliente_simulado(Registro(pagina([ITEM_CRUD]))) as http:
        (v,) = await crear(http).buscar_cercanos(4.711, -74.0721, 500, None, None)
    assert (v.id, v.tipo, v.bateria_pct, v.estado, v.localidad) == ("veh-0016", "bicicleta", 59, "disponible", "Suba")
    assert (v.lat, v.lng) == (4.711, -74.07165)  # el GeoJSON viene [longitud, latitud]
    assert v.distancia_m == 49.9
    assert v.actualizado_en.tzinfo is not None and v.actualizado_en.utcoffset() == timezone.utc.utcoffset(None)


async def test_un_vehiculo_sin_distancia_ni_localidad_se_lee_igual():
    item = {k: v for k, v in ITEM_CRUD.items() if k not in ("distanciaMetros", "localidad")}
    async with cliente_simulado(Registro(pagina([item]))) as http:
        (v,) = await crear(http).listar_todos()
    assert v.distancia_m is None and v.localidad is None


async def test_lee_todas_las_paginas_hasta_completar_el_total():
    items = [{**ITEM_CRUD, "id": f"v{i}"} for i in range(5)]
    reg = Registro(pagina(items[0:2], total=5), pagina(items[2:4], total=5), pagina(items[4:], total=5))
    async with cliente_simulado(reg) as http:
        vehiculos = await crear(http, tamano_pagina=2).listar_todos()
    assert [v.id for v in vehiculos] == [f"v{i}" for i in range(5)]
    assert [p.url.params["pagina"] for p in reg.peticiones] == ["1", "2", "3"]
    assert all(p.url.params["tamano"] == "2" for p in reg.peticiones)


async def test_no_pide_mas_paginas_de_las_necesarias():
    reg = Registro(pagina([ITEM_CRUD], total=1))
    async with cliente_simulado(reg) as http:
        await crear(http).listar_todos()
    assert len(reg.peticiones) == 1


async def test_una_pagina_vacia_corta_el_ciclo_aunque_el_total_diga_mas():
    reg = Registro(pagina([ITEM_CRUD], total=50), pagina([], total=50))
    async with cliente_simulado(reg) as http:
        assert len(await crear(http).listar_todos()) == 1
    assert len(reg.peticiones) == 2


async def test_el_limite_de_paginas_evita_leer_sin_fin_y_deja_un_aviso(caplog):
    reg = Registro(pagina([ITEM_CRUD, {**ITEM_CRUD, "id": "otro"}], total=1000))
    with caplog.at_level(logging.WARNING):
        async with cliente_simulado(reg) as http:
            vehiculos = await crear(http, max_paginas=3, tamano_pagina=2).listar_todos()
    assert len(vehiculos) == 6 and len(reg.peticiones) == 3
    assert "más de" in caplog.text


@pytest.mark.parametrize("falla", [httpx.Response(503), httpx.ReadTimeout("lento"), httpx.ConnectError("caído")])
async def test_si_el_crud_esta_caido_reintenta_y_luego_falla(falla):
    reg = Registro(falla)
    async with cliente_simulado(reg) as http:
        with pytest.raises(ServicioNoDisponible) as e:
            await crear(http).listar_todos()
    assert e.value.servicio == "flota-crud" and len(reg.peticiones) == 3


async def test_un_secreto_equivocado_es_un_error_claro_y_no_se_reintenta():
    reg = Registro(httpx.Response(401, json={"codigo": "gateway_no_autorizado"}))
    async with cliente_simulado(reg) as http:
        with pytest.raises(ServicioNoDisponible) as e:
            await crear(http).listar_todos()
    assert e.value.motivo == "http_401" and len(reg.peticiones) == 1


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(200, json={"items": [{"id": "x"}], "total": 1}),  # falta casi todo
        httpx.Response(200, json={"total": 1}),  # sin items
        httpx.Response(200, json=[]),
        pagina([{**ITEM_CRUD, "actualizadoEn": "ayer"}]),
        pagina([{**ITEM_CRUD, "ubicacion": {"type": "Point", "coordinates": [1]}}]),
    ],
)
async def test_una_respuesta_con_otra_forma_no_se_interpreta(respuesta):
    async with cliente_simulado(Registro(respuesta)) as http:
        with pytest.raises(ServicioNoDisponible) as e:
            await crear(http).listar_todos()
    assert e.value.motivo == "respuesta_inesperada"


async def test_una_respuesta_que_no_es_json_se_rechaza():
    async with cliente_simulado(Registro(httpx.Response(200, text="<html>"))) as http:
        with pytest.raises(ServicioNoDisponible) as e:
            await crear(http).listar_todos()
    assert e.value.motivo == "respuesta_no_json"
