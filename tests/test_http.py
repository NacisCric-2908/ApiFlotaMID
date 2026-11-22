import httpx
import pytest

from app.adaptadores.salida.http import enviar, json_o_error
from app.dominio.errores import ServicioNoDisponible
from tests.fakes import Registro, cliente_simulado


async def llamar(registro, reintentos=2):
    async with cliente_simulado(registro) as http:
        return await enviar(http, "svc", "GET", "http://x/", reintentos=reintentos, backoff_s=0)


async def test_reintenta_los_fallos_transitorios_y_se_recupera():
    reg = Registro(httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"ok": 1}))
    assert (await llamar(reg)).status_code == 200
    assert len(reg.peticiones) == 3


async def test_reintenta_ante_429():
    reg = Registro(httpx.Response(429), httpx.Response(200))
    assert (await llamar(reg)).status_code == 200


@pytest.mark.parametrize(
    ("falla", "motivo"),
    [
        (httpx.Response(500), "http_500"),
        (httpx.Response(503), "http_503"),
        (httpx.ReadTimeout("lento"), "ReadTimeout"),
        (httpx.ConnectError("caído"), "ConnectError"),
    ],
)
async def test_agotados_los_reintentos_lanza_servicio_no_disponible(falla, motivo):
    reg = Registro(falla)
    with pytest.raises(ServicioNoDisponible) as e:
        await llamar(reg, reintentos=2)
    assert (e.value.servicio, e.value.motivo) == ("svc", motivo)
    assert len(reg.peticiones) == 3  # el intento inicial y 2 reintentos


@pytest.mark.parametrize("estado", [400, 401, 403, 404])
async def test_un_4xx_no_se_reintenta_y_se_devuelve_para_que_decida_quien_llama(estado):
    reg = Registro(httpx.Response(estado))
    assert (await llamar(reg)).status_code == estado
    assert len(reg.peticiones) == 1


def test_json_de_una_respuesta_200():
    assert json_o_error("svc", httpx.Response(200, json={"a": 1})) == {"a": 1}


@pytest.mark.parametrize(("respuesta", "motivo"), [(httpx.Response(404), "http_404"), (httpx.Response(200, text="<html>"), "respuesta_no_json")])
def test_json_de_una_respuesta_mala_es_un_servicio_no_disponible(respuesta, motivo):
    with pytest.raises(ServicioNoDisponible) as e:
        json_o_error("svc", respuesta)
    assert e.value.motivo == motivo
