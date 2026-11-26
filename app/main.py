import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.adaptadores.entrada import api, salud
from app.adaptadores.entrada.dependencias import Contenedor
from app.adaptadores.entrada.errores import registrar_manejadores
from app.adaptadores.entrada.openapi import instalar_contrato
from app.adaptadores.entrada.seguridad import GatewaySecretMiddleware
from app.adaptadores.salida.reloj import RelojSistema
from app.adaptadores.salida.token import TokenGateway
from app.adaptadores.salida.vehiculos_http import VehiculosHttp
from app.adaptadores.salida.zonas_http import ZonasHttp
from app.config import get_settings
from app.dominio.puertos import RelojPort, VehiculosPort, ZonasPort

VERSION = "0.1.0"


def crear_app(
    vehiculos: VehiculosPort | None = None, zonas: ZonasPort | None = None, reloj: RelojPort | None = None
) -> FastAPI:
    """Arma la aplicación. Los puertos que no se pasen se construyen con los adaptadores reales (HTTP).

    Pasar puertos simulados es lo que permite probar la API sin red ni otros servicios.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = get_settings()
        logging.basicConfig(level=settings.log_level.upper())
        http: httpx.AsyncClient | None = None
        if vehiculos is None or zonas is None:
            http = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.externos_timeout_s), headers={"User-Agent": f"ApiFlotaMID/{VERSION}"}
            )
        reintentos, backoff = settings.externos_reintentos, settings.externos_backoff_s
        puerto_vehiculos = vehiculos or VehiculosHttp(
            http, settings.flota_crud_url, settings.flota_crud_secret,
            reintentos=reintentos, backoff_s=backoff, max_paginas=settings.max_paginas,
        )  # fmt: skip
        puerto_zonas = zonas
        if puerto_zonas is None:
            tokens = TokenGateway(
                http, settings.url_token, settings.client_id, settings.client_secret, settings.token_scope,
                reintentos=reintentos, backoff_s=backoff,
            )  # fmt: skip
            puerto_zonas = ZonasHttp(
                http, settings.gateway_url, settings.zonas_ruta, tokens, reintentos=reintentos, backoff_s=backoff
            )
        app.state.contenedor = Contenedor(
            vehiculos=puerto_vehiculos,
            zonas=puerto_zonas,
            reloj=reloj or RelojSistema(),
            reglas_recomendacion=settings.reglas_recomendacion(),
            reglas_alertas=settings.reglas_alertas(),
        )
        yield
        if http is not None:
            await http.aclose()

    app = FastAPI(
        title="API Flota MID - Recomendaciones y alertas",
        version=VERSION,
        description=(
            "MID de Flota del clúster Rodar: recomienda los mejores vehículos cerca de un punto y lista las alertas "
            "operativas de la flota. Combina el CRUD de Flota con las zonas de Viajes y zonas."
        ),
        lifespan=lifespan,
        # Etiquetas y operationId en ASCII y sin guiones bajos: los generadores de clientes producen nombres limpios.
        openapi_tags=[
            {"name": "Recomendaciones", "description": "Los mejores vehículos cerca de un punto."},
            {"name": "Alertas", "description": "Vehículos que requieren atención del equipo operativo."},
            {"name": "Salud", "description": "Estado del servicio (público, sin token)."},
        ],
    )
    registrar_manejadores(app)
    instalar_contrato(app)
    app.add_middleware(GatewaySecretMiddleware)
    app.include_router(salud.router)
    app.include_router(api.router)
    return app


app = crear_app()
