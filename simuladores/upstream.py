"""Simulador de los servicios de los que depende el MID de Flota. SOLO para desarrollo y pruebas.

Imita, con los datos semilla acordados:
  - el CRUD de Flota:        GET /vehiculos (filtros, cercanía, paginación) y GET /health, con su cabecera secreta;
  - Viajes y zonas:          GET /viajes/zonas/verificar, con token Bearer;
  - el token del gateway:    POST /token (OAuth2 client credentials).

Los 30 vehículos y las 4 zonas son los mismos que documenta el CRUD de Flota (semilla.md), así que lo que el
MID devuelve aquí es lo que debe devolver con los servicios reales. No es una réplica completa: solo lo que el
MID usa.
"""

import math
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

RADIO_TIERRA_M = 6_378_137

# ---- Datos semilla del CRUD de Flota (cuadrícula de 6 x 5 en Suba, Bogotá) ----
CENTRO_LAT, CENTRO_LNG, PASO, COLUMNAS, FILAS = 4.7110, -74.0721, 0.0009, 6, 5
BATERIAS = [
    92, 78, 64, 55, 41, 88, 30, 73, 12, 95,
    22, 67, 48, 81, 9, 59, 35, 70, 14, 84,
    26, 61, 45, 90, 18, 77, 52, 38, 66, 24,
]  # fmt: skip
SIN_ACTUALIZAR = {7, 20}  # ubicación vieja (más de 2 h)

# ---- Zonas propuestas por Flota a Viajes y zonas: (lng_min, lat_min, lng_max, lat_max) ----
ZONAS = [
    {"nombre": "Prohibida Centro", "tipo": "prohibida", "caja": (-74.0719, 4.7107, -74.0714, 4.7113)},
    {"nombre": "Recargo Oriente", "tipo": "recargo", "caja": (-74.0710, 4.7086, -74.0694, 4.7134)},
    {"nombre": "Parqueo Occidente", "tipo": "parqueo", "caja": (-74.0748, 4.7086, -74.0730, 4.7134)},
    {"nombre": "Parqueo Sur", "tipo": "parqueo", "caja": (-74.0730, 4.7086, -74.0710, 4.7100)},
]


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def generar_vehiculos(ahora: datetime) -> list[dict]:
    vehiculos = []
    for i in range(COLUMNAS * FILAS):
        col, fila = i % COLUMNAS, i // COLUMNAS
        lng = CENTRO_LNG + (col - (COLUMNAS - 1) / 2) * PASO
        lat = CENTRO_LAT + (fila - (FILAS - 1) / 2) * PASO
        estado = "mantenimiento" if i % 10 == 9 else "en_viaje" if i in (5, 17) else "disponible"
        vehiculos.append(
            {
                "id": f"veh-{i + 1:04d}",
                "tipo": "scooter" if i % 2 == 0 else "bicicleta",
                "bateriaPct": BATERIAS[i],
                "estado": estado,
                "ubicacion": {"type": "Point", "coordinates": [round(lng, 6), round(lat, 6)]},
                "localidad": {"codigo": "11", "nombre": "Suba"},
                "actualizadoEn": _iso(ahora - timedelta(hours=3 if i in SIN_ACTUALIZAR else 0, minutes=i)),
            }
        )
    return vehiculos


def distancia_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    f1, f2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((f2 - f1) / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(a))


def zonas_de(lng: float, lat: float) -> list[dict]:
    return [
        {"nombre": z["nombre"], "tipo": z["tipo"]}
        for z in ZONAS
        if z["caja"][0] <= lng <= z["caja"][2] and z["caja"][1] <= lat <= z["caja"][3]
    ]


def crear_simulador(
    ahora: datetime | None = None, crud_secret: str | None = None, client_id: str | None = None, client_secret: str | None = None
) -> FastAPI:
    app = FastAPI(title="Simulador de servicios de Flota (solo desarrollo)")
    crud_secret = crud_secret or os.environ.get("CRUD_SECRET", "secreto-del-crud-simulado")
    client_id = client_id or os.environ.get("CLIENT_ID", "mid-flota")
    client_secret = client_secret or os.environ.get("CLIENT_SECRET", "secreto-del-mid-simulado")

    app.state.vehiculos = generar_vehiculos(ahora or datetime.now(timezone.utc))
    app.state.tokens_vigentes: set[str] = set()
    app.state.tokens_emitidos = 0
    # Para provocar fallos desde las pruebas: crud_caido / zonas_caidas / gateway_caido = True
    app.state.crud_caido = app.state.zonas_caidas = app.state.gateway_caido = False

    def caido(request: Request, bandera: str) -> None:
        if getattr(request.app.state, bandera):
            raise HTTPException(503, "simulador: servicio caído a propósito")

    # ----------------------------- token del gateway -----------------------------
    @app.post("/token")
    async def token(request: Request):
        caido(request, "gateway_caido")
        # Formulario application/x-www-form-urlencoded, leído a mano para no depender de python-multipart.
        datos = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
        if datos.get("grant_type") != "client_credentials" or (datos.get("client_id"), datos.get("client_secret")) != (
            client_id,
            client_secret,
        ):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        request.app.state.tokens_emitidos += 1
        valor = f"token-simulado-{request.app.state.tokens_emitidos}"
        request.app.state.tokens_vigentes.add(valor)
        return {"access_token": valor, "token_type": "bearer", "expires_in": 300, "scope": datos.get("scope", "")}

    # ----------------------------- Viajes y zonas -----------------------------
    @app.get("/viajes/zonas/verificar")
    async def verificar(
        request: Request,
        lat: Annotated[float, Query(ge=-90, le=90)],
        lng: Annotated[float, Query(ge=-180, le=180)],
        authorization: Annotated[str | None, Header()] = None,
    ):
        caido(request, "zonas_caidas")
        recibido = (authorization or "").removeprefix("Bearer ")
        if recibido not in request.app.state.tokens_vigentes:
            return JSONResponse({"codigo": "no_autorizado", "mensaje": "Token inválido", "detalle": {}}, status_code=401)
        zonas = zonas_de(lng, lat)
        return {"permitida": not any(z["tipo"] == "prohibida" for z in zonas), "zonas": zonas}

    # ----------------------------- CRUD de Flota -----------------------------
    def exigir_secreto(request: Request, x_gateway_secret: Annotated[str | None, Header()] = None) -> None:
        caido(request, "crud_caido")
        if x_gateway_secret != crud_secret:
            raise HTTPException(401, "La petición debe llegar a través del API Gateway.")

    @app.get("/vehiculos", dependencies=[Depends(exigir_secreto)])
    async def listar(
        request: Request,
        tipo: str | None = None,
        estado: str | None = None,
        bateriaMin: Annotated[int | None, Query(ge=0, le=100)] = None,
        lat: float | None = None,
        lng: float | None = None,
        radioMetros: Annotated[float | None, Query(gt=0, le=50_000)] = None,
        pagina: Annotated[int, Query(ge=1)] = 1,
        tamano: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        if (lat is None) != (lng is None) or (radioMetros is not None and lat is None):
            raise HTTPException(400, "Los parámetros 'lat' y 'lng' van juntos.")
        items = [dict(v) for v in request.app.state.vehiculos]
        if tipo:
            items = [v for v in items if v["tipo"] == tipo]
        if estado:
            items = [v for v in items if v["estado"] == estado]
        if bateriaMin is not None:
            items = [v for v in items if v["bateriaPct"] >= bateriaMin]
        if lat is not None:
            radio = radioMetros or 500
            for v in items:
                v["distanciaMetros"] = round(distancia_m(lat, lng, v["ubicacion"]["coordinates"][1], v["ubicacion"]["coordinates"][0]), 1)
            items = sorted((v for v in items if v["distanciaMetros"] <= radio), key=lambda v: (v["distanciaMetros"], v["id"]))
        desde = (pagina - 1) * tamano
        return {"items": items[desde : desde + tamano], "pagina": pagina, "tamano": tamano, "total": len(items)}

    @app.get("/health")
    async def health():
        return {"estado": "ok"}

    return app


app = crear_simulador()
