import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from app.adaptadores.salida.token import TokenGateway
from app.dominio.errores import ServicioNoDisponible
from tests.fakes import Registro, cliente_simulado


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def token_ok(valor="t1", expira=100):
    return httpx.Response(200, json={"access_token": valor, "token_type": "bearer", "expires_in": expira})


def crear(http, reloj=None):
    return TokenGateway(http, "http://gw/token", "mid-flota", "secreto", "zonas:leer",
                        reintentos=2, backoff_s=0, reloj=reloj or Reloj())


async def test_pide_el_token_con_el_flujo_client_credentials():
    reg = Registro(token_ok())
    async with cliente_simulado(reg) as http:
        assert await crear(http).obtener() == "t1"
    (p,) = reg.peticiones
    assert (p.method, str(p.url)) == ("POST", "http://gw/token")
    assert p.headers["content-type"] == "application/x-www-form-urlencoded"
    assert {k: v[0] for k, v in parse_qs(p.content.decode()).items()} == {
        "grant_type": "client_credentials", "client_id": "mid-flota", "client_secret": "secreto", "scope": "zonas:leer",
    }


async def test_guarda_el_token_hasta_que_esta_por_vencer():
    reloj, reg = Reloj(), Registro(token_ok("t1", expira=100), token_ok("t2", expira=100))
    async with cliente_simulado(reg) as http:
        tokens = crear(http, reloj)
        assert await tokens.obtener() == "t1"
        reloj.t += 69  # vigencia 100 s menos 30 s de margen = 70 s
        assert await tokens.obtener() == "t1"
        assert len(reg.peticiones) == 1
        reloj.t += 2  # ya pasó el margen: se renueva antes de que venza de verdad
        assert await tokens.obtener() == "t2"
        assert len(reg.peticiones) == 2


async def test_invalidar_obliga_a_pedir_uno_nuevo():
    reg = Registro(token_ok("t1"), token_ok("t2"))
    async with cliente_simulado(reg) as http:
        tokens = crear(http)
        await tokens.obtener()
        tokens.invalidar()
        assert await tokens.obtener() == "t2"


async def test_peticiones_simultaneas_comparten_una_sola_solicitud():
    llamadas = []

    async def handler(request):
        llamadas.append(request)
        await asyncio.sleep(0.01)
        return token_ok()

    async with cliente_simulado(handler) as http:
        tokens = crear(http)
        resultados = await asyncio.gather(*(tokens.obtener() for _ in range(10)))
    assert resultados == ["t1"] * 10 and len(llamadas) == 1


async def test_sin_expires_in_usa_5_minutos_menos_el_margen():
    reloj, reg = Reloj(), Registro(httpx.Response(200, json={"access_token": "t1"}), token_ok("t2"))
    async with cliente_simulado(reg) as http:
        tokens = crear(http, reloj)
        await tokens.obtener()
        reloj.t += 269
        assert await tokens.obtener() == "t1"
        reloj.t += 2
        assert await tokens.obtener() == "t2"


@pytest.mark.parametrize(
    ("respuesta", "motivo"),
    [
        (httpx.Response(401), "http_401"),
        (httpx.Response(400, json={"error": "invalid_client"}), "http_400"),
        (httpx.Response(200, json={"token_type": "bearer"}), "respuesta_inesperada"),
        (httpx.Response(200, json={"access_token": ""}), "respuesta_inesperada"),
        (httpx.Response(200, text="<html>"), "respuesta_inesperada"),
        (httpx.Response(200, json=["no", "es", "un", "objeto"]), "respuesta_inesperada"),
    ],
)
async def test_un_token_que_no_se_puede_obtener_es_servicio_no_disponible(respuesta, motivo):
    async with cliente_simulado(Registro(respuesta)) as http:
        with pytest.raises(ServicioNoDisponible) as e:
            await crear(http).obtener()
    assert (e.value.servicio, e.value.motivo) == ("gateway-token", motivo)


async def test_si_el_gateway_esta_caido_reintenta_y_luego_falla():
    reg = Registro(httpx.ConnectError("caído"))
    async with cliente_simulado(reg) as http:
        with pytest.raises(ServicioNoDisponible):
            await crear(http).obtener()
    assert len(reg.peticiones) == 3
