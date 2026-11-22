import httpx
import pytest

from app.adaptadores.salida.token import TokenGateway
from app.adaptadores.salida.zonas_http import ZonasHttp
from app.dominio.errores import ServicioNoDisponible
from tests.fakes import cliente_simulado


class Gateway:
    """Simula el gateway: /token y /viajes/zonas/verificar. `zonas` es una lista de respuestas, en orden."""

    def __init__(self, zonas, tokens=("t1", "t2", "t3")):
        self.zonas, self.tokens = list(zonas), list(tokens)
        self.peticiones_zonas: list[httpx.Request] = []
        self.peticiones_token = 0

    def __call__(self, request: httpx.Request):
        if request.url.path == "/token":
            self.peticiones_token += 1
            return httpx.Response(200, json={"access_token": self.tokens[self.peticiones_token - 1], "expires_in": 300})
        self.peticiones_zonas.append(request)
        r = self.zonas[min(len(self.peticiones_zonas), len(self.zonas)) - 1]
        if isinstance(r, Exception):
            raise r
        return r


def crear(http):
    tokens = TokenGateway(http, "http://gw/token", "mid-flota", "secreto", "zonas:leer", reintentos=2, backoff_s=0)
    return ZonasHttp(http, "http://gw/", "/viajes/zonas/verificar", tokens, reintentos=2, backoff_s=0)


async def consultar(gw, lat=4.711, lng=-74.07165):
    async with cliente_simulado(gw) as http:
        return await crear(http).esta_en_zona_prohibida(lat, lng)


async def test_permitida_false_significa_zona_prohibida():
    gw = Gateway([httpx.Response(200, json={"permitida": False, "zonas": [{"nombre": "Prohibida Centro", "tipo": "prohibida"}]})])
    assert await consultar(gw) is True


async def test_permitida_true_significa_que_no_esta_en_zona_prohibida():
    assert await consultar(Gateway([httpx.Response(200, json={"permitida": True, "zonas": []})])) is False


async def test_llama_por_el_gateway_con_el_token_y_las_coordenadas():
    gw = Gateway([httpx.Response(200, json={"permitida": True, "zonas": []})])
    await consultar(gw, lat=4.711, lng=-74.07165)
    (p,) = gw.peticiones_zonas
    assert (p.url.host, p.url.path) == ("gw", "/viajes/zonas/verificar")
    assert dict(p.url.params) == {"lat": "4.711", "lng": "-74.07165"}  # ojo: aquí lat y lng van por separado
    assert p.headers["authorization"] == "Bearer t1"


async def test_reutiliza_el_token_entre_consultas():
    gw = Gateway([httpx.Response(200, json={"permitida": True})])
    async with cliente_simulado(gw) as http:
        zonas = crear(http)
        for _ in range(3):
            await zonas.esta_en_zona_prohibida(4.7, -74.0)
    assert gw.peticiones_token == 1 and len(gw.peticiones_zonas) == 3


async def test_si_viajes_responde_401_renueva_el_token_y_reintenta_una_vez():
    gw = Gateway([httpx.Response(401), httpx.Response(200, json={"permitida": False})])
    assert await consultar(gw) is True
    assert gw.peticiones_token == 2
    assert [p.headers["authorization"] for p in gw.peticiones_zonas] == ["Bearer t1", "Bearer t2"]


async def test_si_sigue_el_401_despues_de_renovar_falla_en_vez_de_insistir():
    gw = Gateway([httpx.Response(401)])
    with pytest.raises(ServicioNoDisponible) as e:
        await consultar(gw)
    assert (e.value.servicio, e.value.motivo) == ("viajes-zonas", "http_401")
    assert gw.peticiones_token == 2 and len(gw.peticiones_zonas) == 2


async def test_un_403_por_falta_de_alcance_es_un_servicio_no_disponible_sin_reintentar():
    gw = Gateway([httpx.Response(403)])
    with pytest.raises(ServicioNoDisponible) as e:
        await consultar(gw)
    assert e.value.motivo == "http_403" and len(gw.peticiones_zonas) == 1


@pytest.mark.parametrize("falla", [httpx.Response(503), httpx.ReadTimeout("lento"), httpx.ConnectError("caído")])
async def test_si_viajes_y_zonas_esta_caido_reintenta_y_luego_falla(falla):
    gw = Gateway([falla])
    with pytest.raises(ServicioNoDisponible) as e:
        await consultar(gw)
    assert e.value.servicio == "viajes-zonas" and len(gw.peticiones_zonas) == 3


@pytest.mark.parametrize(
    "cuerpo",
    [{"zonas": []}, {"permitida": "false"}, {"permitida": None}, ["permitida"], "texto"],
)
async def test_una_respuesta_sin_permitida_booleana_no_se_interpreta(cuerpo):
    with pytest.raises(ServicioNoDisponible) as e:
        await consultar(Gateway([httpx.Response(200, json=cuerpo)]))
    assert e.value.motivo == "respuesta_inesperada"


async def test_si_el_gateway_no_da_token_el_error_lo_dice():
    def handler(request):
        return httpx.Response(401) if request.url.path == "/token" else httpx.Response(200, json={"permitida": True})

    async with cliente_simulado(handler) as http:
        with pytest.raises(ServicioNoDisponible) as e:
            await crear(http).esta_en_zona_prohibida(4.7, -74.0)
    assert e.value.servicio == "gateway-token"
