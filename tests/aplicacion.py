from contextlib import asynccontextmanager

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import crear_app
from tests.fakes import RelojFalso, VehiculosFalso, ZonasFalso

SECRETO = "test-secret"


@asynccontextmanager
async def cliente_api(vehiculos=None, zonas=None, reloj=None, secreto: str | None = SECRETO):
    """Cliente HTTP contra la aplicación completa, con puertos simulados (sin red).

    `raise_app_exceptions=False`: un error inesperado debe verse como el 500 que recibiría un cliente real.
    """
    app = crear_app(vehiculos or VehiculosFalso(), zonas or ZonasFalso(), reloj or RelojFalso())
    async with LifespanManager(app) as manager:
        transporte = ASGITransport(app=manager.app, raise_app_exceptions=False)
        cabeceras = {"X-Gateway-Secret": secreto} if secreto else {}
        async with AsyncClient(transport=transporte, base_url="http://test", headers=cabeceras) as cliente:
            yield cliente
