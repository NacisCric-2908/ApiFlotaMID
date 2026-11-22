"""Variables de entorno de prueba (por si se corre pytest fuera de docker compose) y fábrica de clientes."""

import os

for clave, valor in {
    "GATEWAY_SECRET": "test-secret",
    "FLOTA_CRUD_URL": "http://crud.prueba",
    "FLOTA_CRUD_SECRET": "secreto-crud-prueba",
    "GATEWAY_URL": "http://gateway.prueba",
    "CLIENT_ID": "mid-flota",
    "CLIENT_SECRET": "secreto-mid-prueba",
    "EXTERNOS_BACKOFF_S": "0",
}.items():
    os.environ.setdefault(clave, valor)
